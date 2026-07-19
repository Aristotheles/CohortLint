"""Safe metadata harmonization and provenance output."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from cohortlint import __version__
from cohortlint.config import CohortLintConfig
from cohortlint.loader import load_metadata
from cohortlint.rules.vocabulary import OntologyMapping, mappings_for

SSSOM_COLUMNS = [
    "subject_id",
    "subject_label",
    "predicate_id",
    "object_id",
    "object_label",
    "mapping_justification",
    "confidence",
]


def _categorical_map(config: CohortLintConfig, column: str) -> dict[str, str]:
    schema = config.schema_[column]
    mapping = {str(value).casefold(): str(value) for value in schema.allowed}
    for canonical, synonyms in schema.synonyms.items():
        mapping[str(canonical).casefold()] = str(canonical)
        mapping.update({str(value).casefold(): str(canonical) for value in synonyms})
    return mapping


def _ontology_maps(
    config: CohortLintConfig, frame: pd.DataFrame
) -> dict[str, dict[str, OntologyMapping]]:
    result: dict[str, dict[str, OntologyMapping]] = {}
    for column, schema in config.schema_.items():
        if schema.type == "ontology" and schema.ontology and column in frame:
            terms = sorted(str(value) for value in frame[column].dropna().unique())
            result[column] = mappings_for(terms, schema.ontology)
    return result


def harmonize_metadata(
    config: CohortLintConfig,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    loaded = load_metadata(config)
    frame = loaded.merged.drop(columns=["__sample_id__"], errors="ignore").copy()
    provenance: list[dict[str, Any]] = []
    for column, schema in config.schema_.items():
        if column not in frame:
            continue
        if schema.type == "categorical":
            value_map = _categorical_map(config, column)

            def normalize(value: Any, mapping: dict[str, str] = value_map) -> Any:
                if pd.isna(value):
                    return value
                return mapping.get(str(value).casefold(), value)

            before = frame[column].copy()
            frame[column] = frame[column].map(normalize)
            changed = int((before.astype(str) != frame[column].astype(str)).sum())
            if changed:
                provenance.append({"rule_id": "U002", "column": column, "changed": changed})
        elif schema.type == "numeric":
            text = frame[column].astype("string")
            mask = text.str.fullmatch(r"-?\d+,\d+", na=False)
            if mask.any():
                frame.loc[mask, column] = text.loc[mask].str.replace(",", ".", regex=False)
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
                provenance.append({"rule_id": "U003", "column": column, "changed": int(mask.sum())})
    sssom: list[dict[str, Any]] = []
    for column, mappings in _ontology_maps(config, frame).items():
        accepted = {
            term: mapping for term, mapping in mappings.items() if mapping.confidence >= 0.95
        }
        if not accepted:
            continue
        before = frame[column].copy()

        def normalize_ontology(
            value: Any, accepted_mappings: dict[str, OntologyMapping] = accepted
        ) -> Any:
            if pd.isna(value):
                return value
            mapping = accepted_mappings.get(str(value))
            return mapping.object_id if mapping is not None else value

        frame[column] = frame[column].map(normalize_ontology)
        changed = int((before.astype(str) != frame[column].astype(str)).sum())
        if changed:
            provenance.append({"rule_id": "V003", "column": column, "changed": changed})
        for term, mapping in accepted.items():
            sssom.append(
                {
                    "subject_id": term,
                    "subject_label": term,
                    "predicate_id": "skos:exactMatch",
                    "object_id": mapping.object_id,
                    "object_label": mapping.object_label,
                    "mapping_justification": "semapv:LexicalMatching",
                    "confidence": mapping.confidence,
                }
            )
    return frame, provenance, sssom


def write_harmonized(
    frame: pd.DataFrame,
    provenance: list[dict[str, Any]],
    sssom: list[dict[str, Any]],
    output: Path,
    mappings_output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    provenance_path = output.with_suffix(output.suffix + ".provenance.json")
    provenance_path.write_text(
        json.dumps(
            {
                "cohortlint_version": __version__,
                "generated_at": datetime.now(UTC).isoformat(),
                "transformations": provenance,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    mappings_output.parent.mkdir(parents=True, exist_ok=True)
    with mappings_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SSSOM_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(sssom)
