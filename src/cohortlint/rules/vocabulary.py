"""Optional ontology vocabulary rules V001-V003."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from cohortlint.config import CohortLintConfig
from cohortlint.model import Finding, RuleContext, Severity
from cohortlint.registry import rule

_CACHE_LIMIT = 10 * 1024 * 1024


class OntologyMapping(BaseModel):
    subject_label: str
    object_id: str
    object_label: str
    confidence: float = Field(ge=0, le=1)


def _config(ctx: RuleContext) -> CohortLintConfig:
    if isinstance(ctx.config, CohortLintConfig):
        return ctx.config
    return CohortLintConfig.model_validate(ctx.config)


def _cache_path(ontology: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", ontology)[:100]
    return Path(".cohortlint_cache") / f"{safe_name}.json"


def _read_cache(ontology: str) -> dict[str, OntologyMapping]:
    path = _cache_path(ontology)
    if not path.exists() or path.stat().st_size > _CACHE_LIMIT:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("ontology_version") != ontology:
            return {}
        return {
            label: OntologyMapping.model_validate(mapping)
            for label, mapping in payload.get("mappings", {}).items()
        }
    except (OSError, json.JSONDecodeError, ValidationError, AttributeError):
        return {}


def _write_cache(ontology: str, mappings: dict[str, OntologyMapping]) -> None:
    path = _cache_path(ontology)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to overwrite symlinked ontology cache: {path}")
    payload = {
        "ontology_version": ontology,
        "mappings": {label: mapping.model_dump() for label, mapping in mappings.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _column_value(row: pd.Series[Any], names: tuple[str, ...], default: Any = None) -> Any:
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return default


def _map_live(terms: list[str], ontology: str) -> dict[str, OntologyMapping]:
    import text2term  # type: ignore[import-not-found]

    result = text2term.map_terms(
        source_terms=terms,
        target_ontology=ontology,
        min_score=0.8,
        max_mappings=1,
        incl_unmapped=True,
        cache_folder=str(Path(".cohortlint_cache")),
    )
    mappings: dict[str, OntologyMapping] = {}
    for _, row in result.iterrows():
        source = str(_column_value(row, ("source_term", "source_label", "Source Term"), ""))
        object_id = str(_column_value(row, ("mapped_term_iri", "object_id", "Mapped Term IRI"), ""))
        if not source or not object_id:
            continue
        mappings[source] = OntologyMapping(
            subject_label=source,
            object_id=object_id,
            object_label=str(
                _column_value(row, ("mapped_term_label", "object_label", "Mapped Term Label"), "")
            ),
            confidence=float(
                _column_value(row, ("mapping_score", "confidence", "Mapping Score"), 0)
            ),
        )
    return mappings


def mappings_for(terms: list[str], ontology: str) -> dict[str, OntologyMapping]:
    cached = _read_cache(ontology)
    missing = [term for term in terms if term not in cached]
    if missing and importlib.util.find_spec("text2term") is not None:
        cached.update(_map_live(missing, ontology))
        _write_cache(ontology, cached)
    return cached


def _ontology_inputs(ctx: RuleContext) -> list[tuple[str, str, list[str]]]:
    inputs: list[tuple[str, str, list[str]]] = []
    for column, schema in _config(ctx).schema_.items():
        if schema.type != "ontology" or not schema.ontology:
            continue
        terms = sorted(
            {
                str(value)
                for frame in ctx.cohorts.values()
                if column in frame
                for value in frame[column].dropna().unique()
            }
        )
        inputs.append((column, schema.ontology, terms))
    return inputs


@rule(id="V001", severity=Severity.WARNING, category="vocabulary")
def unmapped_ontology_terms(ctx: RuleContext) -> list[Finding]:
    inputs = _ontology_inputs(ctx)
    if (
        inputs
        and importlib.util.find_spec("text2term") is None
        and all(not _read_cache(ontology) for _, ontology, _ in inputs)
    ):
        return [
            Finding(
                rule_id="V001",
                severity=Severity.INFO,
                message_params={"column": "-", "count": 0},
                evidence={"optional_dependency_missing": True},
            )
        ]
    findings: list[Finding] = []
    for column, ontology, terms in inputs:
        mappings = mappings_for(terms, ontology)
        unmapped = [
            term for term in terms if term not in mappings or mappings[term].confidence < 0.8
        ]
        if unmapped:
            findings.append(
                Finding(
                    rule_id="V001",
                    severity=Severity.WARNING,
                    column=column,
                    message_params={"column": column, "count": len(unmapped)},
                    evidence={"unmapped": unmapped, "ontology": ontology},
                )
            )
    return findings


@rule(id="V002", severity=Severity.INFO, category="vocabulary")
def low_confidence_mappings(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for column, ontology, terms in _ontology_inputs(ctx):
        for term, mapping in mappings_for(terms, ontology).items():
            if 0.8 <= mapping.confidence < 0.95:
                findings.append(
                    Finding(
                        rule_id="V002",
                        severity=Severity.INFO,
                        column=column,
                        message_params={"term": term, "confidence": f"{mapping.confidence:.2f}"},
                        evidence=mapping.model_dump(),
                    )
                )
    return findings


@rule(id="V003", severity=Severity.WARNING, category="vocabulary")
def near_duplicate_labels(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for column, ontology, terms in _ontology_inputs(ctx):
        grouped: dict[str, list[str]] = {}
        for term, mapping in mappings_for(terms, ontology).items():
            if mapping.confidence >= 0.8:
                grouped.setdefault(mapping.object_id, []).append(term)
        duplicates = {object_id: labels for object_id, labels in grouped.items() if len(labels) > 1}
        if duplicates:
            findings.append(
                Finding(
                    rule_id="V003",
                    severity=Severity.WARNING,
                    column=column,
                    message_params={"column": column, "count": len(duplicates)},
                    evidence={"duplicates": duplicates, "ontology": ontology},
                )
            )
    return findings
