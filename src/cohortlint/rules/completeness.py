"""Completeness rules C001-C003."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from cohortlint.config import CohortLintConfig
from cohortlint.model import Finding, RuleContext, Severity
from cohortlint.registry import rule


def _config(ctx: RuleContext) -> CohortLintConfig:
    return (
        ctx.config
        if isinstance(ctx.config, CohortLintConfig)
        else CohortLintConfig.model_validate(ctx.config)
    )


@rule(id="C001", severity=Severity.ERROR, category="completeness")
def required_covariate_absent(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    required = [name for name, schema in _config(ctx).schema_.items() if schema.required]
    for name, frame in ctx.cohorts.items():
        for column in required:
            if column not in frame:
                findings.append(
                    Finding(
                        rule_id="C001",
                        severity=Severity.ERROR,
                        cohort=name,
                        column=column,
                        message_params={"column": column},
                        evidence={},
                    )
                )
    return findings


@rule(id="C002", severity=Severity.WARNING, category="completeness")
def high_missingness(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    config = _config(ctx)
    for name, frame in ctx.cohorts.items():
        for column in config.schema_:
            if column not in frame or frame.empty:
                continue
            fraction = float(frame[column].isna().mean())
            if fraction > config.rules.missingness_fraction:
                findings.append(
                    Finding(
                        rule_id="C002",
                        severity=Severity.WARNING,
                        cohort=name,
                        column=column,
                        message_params={"column": column, "fraction": f"{fraction:.1%}"},
                        evidence={"fraction": fraction},
                    )
                )
    return findings


def _benjamini_hochberg(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 1.0
    for rank_index in range(len(p_values) - 1, -1, -1):
        original_index = int(order[rank_index])
        rank = rank_index + 1
        running = min(running, p_values[original_index] * len(p_values) / rank)
        adjusted[original_index] = running
    return adjusted.tolist()


@rule(id="C003", severity=Severity.WARNING, category="completeness")
def differential_missingness(ctx: RuleContext) -> list[Finding]:
    config = _config(ctx)
    biological = [name for name, schema in config.schema_.items() if schema.role == "biological"]
    if not biological:
        return []
    outcome = biological[0]
    tests: list[tuple[str, str, float]] = []
    for cohort, frame in ctx.cohorts.items():
        if outcome not in frame:
            continue
        for column in config.schema_:
            if column == outcome or column not in frame:
                continue
            valid = frame[outcome].notna()
            table = pd.crosstab(frame.loc[valid, column].isna(), frame.loc[valid, outcome])
            if table.shape[0] < 2 or table.shape[1] < 2:
                continue
            try:
                _, p_value, _, _ = chi2_contingency(table)
            except ValueError:
                continue
            tests.append((cohort, column, float(p_value)))
    adjusted = _benjamini_hochberg([item[2] for item in tests])
    return [
        Finding(
            rule_id="C003",
            severity=Severity.WARNING,
            cohort=cohort,
            column=column,
            message_params={"column": column, "biological": outcome, "q_value": f"{q_value:.3g}"},
            evidence={"p_value": p_value, "q_value": q_value},
        )
        for (cohort, column, p_value), q_value in zip(tests, adjusted, strict=True)
        if q_value < config.rules.differential_missingness_alpha
    ]
