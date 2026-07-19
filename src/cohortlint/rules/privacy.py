"""GDPR-relevant privacy hygiene heuristics P001-P003."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from cohortlint.config import CohortLintConfig
from cohortlint.model import Finding, RuleContext, Severity
from cohortlint.registry import rule

_DATE = re.compile(r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\b")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_POSTAL = re.compile(r"\b\d{5}\b")
_NATIONAL_ID = re.compile(r"\b\d{9,12}\b")
_LOCATION_NAME = re.compile(r"address|location|city|postal|zip|ort|adresse", re.IGNORECASE)


def _config(ctx: RuleContext) -> CohortLintConfig:
    if isinstance(ctx.config, CohortLintConfig):
        return ctx.config
    return CohortLintConfig.model_validate(ctx.config)


@rule(id="P001", severity=Severity.ERROR, category="privacy")
def residual_direct_identifiers(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for cohort, frame in ctx.cohorts.items():
        for column in frame.select_dtypes(include=["object", "string"]).columns:
            values = frame[column].dropna().astype(str)
            if values.empty:
                continue
            counts = {
                "date": int(values.str.contains(_DATE).sum()),
                "email": int(values.str.contains(_EMAIL).sum()),
                "national_identifier": int(values.str.contains(_NATIONAL_ID).sum()),
            }
            if _LOCATION_NAME.search(str(column)):
                counts["postal_code"] = int(values.str.contains(_POSTAL).sum())
            counts = {kind: count for kind, count in counts.items() if count}
            if counts:
                findings.append(
                    Finding(
                        rule_id="P001",
                        severity=Severity.ERROR,
                        cohort=cohort,
                        column=str(column),
                        message_params={"column": str(column), "count": sum(counts.values())},
                        evidence={"pattern_counts": counts},
                    )
                )
    return findings


def _quasi_identifiers(config: CohortLintConfig, frame: pd.DataFrame) -> pd.DataFrame:
    data: dict[str, pd.Series[Any]] = {}
    for column, schema in config.schema_.items():
        if column not in frame:
            continue
        if schema.type == "categorical":
            data[column] = frame[column].fillna("<missing>").astype(str)
        elif schema.type == "numeric" and column.casefold() == "age":
            numeric = pd.to_numeric(frame[column], errors="coerce")
            data[f"{column}_5y_bin"] = (np.floor(numeric / 5) * 5).fillna(-1).astype(int)
    return pd.DataFrame(data, index=frame.index)


@rule(id="P002", severity=Severity.WARNING, category="privacy")
def k_anonymity_violation(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    threshold = _config(ctx).privacy.k_anonymity_threshold
    for cohort, frame in ctx.cohorts.items():
        quasi = _quasi_identifiers(_config(ctx), frame)
        if quasi.empty:
            continue
        group_sizes = quasi.groupby(list(quasi.columns), dropna=False).size()
        small = group_sizes[group_sizes < threshold]
        if small.empty:
            continue
        drivers: list[str] = []
        for column in quasi.columns:
            remaining = [name for name in quasi.columns if name != column]
            if not remaining:
                drivers.append(str(column))
                continue
            reduced_sizes = quasi.groupby(remaining, dropna=False).size()
            if reduced_sizes.max() > small.max():
                drivers.append(str(column))
        findings.append(
            Finding(
                rule_id="P002",
                severity=Severity.WARNING,
                cohort=cohort,
                message_params={"count": len(small), "threshold": threshold},
                evidence={
                    "group_sizes": sorted(int(value) for value in small.tolist()),
                    "quasi_identifier_columns": [str(value) for value in quasi.columns],
                    "driving_columns": drivers,
                },
            )
        )
    return findings


@rule(id="P003", severity=Severity.WARNING, category="privacy")
def excessive_date_precision(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for cohort, frame in ctx.cohorts.items():
        for column in frame.columns:
            values = frame[column].dropna()
            if values.empty:
                continue
            if pd.api.types.is_datetime64_any_dtype(values):
                fraction = 1.0
            elif values.dtype == object or pd.api.types.is_string_dtype(values):
                fraction = float(values.astype(str).str.contains(_DATE).mean())
            else:
                continue
            if fraction > 0.8:
                findings.append(
                    Finding(
                        rule_id="P003",
                        severity=Severity.WARNING,
                        cohort=cohort,
                        column=str(column),
                        message_params={"column": str(column)},
                        evidence={"day_precision_fraction": fraction},
                    )
                )
    return findings
