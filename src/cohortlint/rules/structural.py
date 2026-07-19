"""Structural metadata rules S001-S004."""

from __future__ import annotations

from typing import Any

import pandas as pd

from cohortlint.config import CohortLintConfig
from cohortlint.model import Finding, RuleContext, Severity
from cohortlint.registry import rule


def _config(ctx: RuleContext) -> CohortLintConfig:
    if not isinstance(ctx.config, CohortLintConfig):
        raise TypeError("structural rules require CohortLintConfig")
    return ctx.config


@rule(id="S001", severity=Severity.ERROR, category="structural")
def sample_identifier_integrity(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for cohort in _config(ctx).cohorts:
        frame = ctx.cohorts[cohort.name]
        if cohort.sample_id not in frame.columns:
            findings.append(
                Finding(
                    rule_id="S001",
                    severity=Severity.ERROR,
                    cohort=cohort.name,
                    column=cohort.sample_id,
                    message_params={"problem": "missing", "sample_id": cohort.sample_id},
                    evidence={"row_indices": []},
                )
            )
            continue
        values = frame[cohort.sample_id]
        null_rows = frame.index[values.isna()].tolist()
        duplicate_rows = frame.index[values.notna() & values.duplicated(keep=False)].tolist()
        for problem, rows in (("null", null_rows), ("duplicate", duplicate_rows)):
            if rows:
                findings.append(
                    Finding(
                        rule_id="S001",
                        severity=Severity.ERROR,
                        cohort=cohort.name,
                        column=cohort.sample_id,
                        message_params={"problem": problem, "sample_id": cohort.sample_id},
                        evidence={"row_indices": rows},
                    )
                )
    return findings


@rule(id="S002", severity=Severity.WARNING, category="structural")
def observation_level_mixing(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    config = _config(ctx)
    for cohort in config.cohorts:
        frame = ctx.cohorts[cohort.name]
        if cohort.sample_id not in frame.columns:
            continue
        distinct = int(frame[cohort.sample_id].nunique(dropna=True))
        if not distinct:
            continue
        ratio = len(frame) / distinct
        if ratio > config.rules.observation_level_ratio:
            findings.append(
                Finding(
                    rule_id="S002",
                    severity=Severity.WARNING,
                    cohort=cohort.name,
                    column=cohort.sample_id,
                    message_params={"ratio": f"{ratio:.2f}"},
                    evidence={"rows": len(frame), "distinct_samples": distinct, "ratio": ratio},
                )
            )
    return findings


@rule(id="S003", severity=Severity.WARNING, category="structural")
def schema_drift(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    config = _config(ctx)
    cohort_names = [cohort.name for cohort in config.cohorts]
    for column in config.schema_:
        missing = [name for name in cohort_names if column not in ctx.cohorts[name].columns]
        if missing:
            findings.append(
                Finding(
                    rule_id="S003",
                    severity=Severity.WARNING,
                    column=column,
                    message_params={
                        "kind": "missing",
                        "column": column,
                        "cohorts": ", ".join(missing),
                    },
                    evidence={"missing_cohorts": missing},
                )
            )
    declared = set(config.schema_)
    sample_columns = {cohort.sample_id for cohort in config.cohorts}
    extras: dict[str, list[str]] = {}
    for name, frame in ctx.cohorts.items():
        values = sorted(str(column) for column in set(frame.columns) - declared - sample_columns)
        if values:
            extras[name] = values
    if extras:
        findings.append(
            Finding(
                rule_id="S003",
                severity=Severity.INFO,
                message_params={"kind": "extra", "column": "-", "cohorts": ", ".join(extras)},
                evidence={"extra_columns": extras},
            )
        )
    return findings


def _numeric_profile(series: pd.Series[Any]) -> tuple[bool, list[str]]:
    present = series.dropna()
    if present.empty:
        return False, []
    coerced = pd.to_numeric(present, errors="coerce")
    bad = present[coerced.isna()]
    return bad.empty, bad.astype(str).drop_duplicates().head(10).tolist()


@rule(id="S004", severity=Severity.ERROR, category="structural")
def type_disagreement(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for column in _config(ctx).schema_:
        profiles = {
            name: _numeric_profile(frame[column])
            for name, frame in ctx.cohorts.items()
            if column in frame.columns
        }
        if len(profiles) < 2:
            continue
        numeric = [name for name, (is_numeric, _) in profiles.items() if is_numeric]
        non_numeric = [name for name, (is_numeric, _) in profiles.items() if not is_numeric]
        if numeric and non_numeric:
            findings.append(
                Finding(
                    rule_id="S004",
                    severity=Severity.ERROR,
                    column=column,
                    message_params={
                        "column": column,
                        "numeric_cohorts": ", ".join(numeric),
                        "non_numeric_cohorts": ", ".join(non_numeric),
                    },
                    evidence={
                        "offending_values": {name: profiles[name][1] for name in non_numeric}
                    },
                )
            )
    return findings
