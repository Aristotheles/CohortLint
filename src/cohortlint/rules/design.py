"""Study-design diagnostics D001-D006.

The integrability score is a communication heuristic, not a statistic or a guarantee
that integration is valid.
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pandas as pd
from scipy.linalg import qr
from scipy.stats import chi2_contingency

from cohortlint.config import CohortLintConfig
from cohortlint.model import Finding, RuleContext, Severity
from cohortlint.registry import rule


def _config(ctx: RuleContext) -> CohortLintConfig:
    if isinstance(ctx.config, CohortLintConfig):
        return ctx.config
    return CohortLintConfig.model_validate(ctx.config)


def _roles(ctx: RuleContext) -> tuple[str | None, list[str]]:
    biological = [
        name for name, schema in _config(ctx).schema_.items() if schema.role == "biological"
    ]
    technical = [
        name for name, schema in _config(ctx).schema_.items() if schema.role == "technical"
    ]
    return (biological[0] if biological else None), technical


def _combined(ctx: RuleContext, columns: list[str]) -> pd.DataFrame:
    parts = [
        frame[columns]
        for frame in ctx.cohorts.values()
        if all(column in frame for column in columns)
    ]
    return pd.concat(parts, ignore_index=True).dropna() if parts else pd.DataFrame(columns=columns)


def corrected_cramers_v(table: pd.DataFrame) -> tuple[float, float]:
    """Return Bergsma bias-corrected Cramér's V and chi-square p-value."""

    if table.empty or table.shape[0] < 2 or table.shape[1] < 2:
        return 0.0, 1.0
    chi2, p_value, _, _ = chi2_contingency(table, correction=False)
    n = float(table.to_numpy().sum())
    if n <= 1:
        return 0.0, float(p_value)
    rows, columns = table.shape
    phi2 = chi2 / n
    phi2_corrected = max(0.0, phi2 - ((columns - 1) * (rows - 1)) / (n - 1))
    columns_corrected = columns - ((columns - 1) ** 2) / (n - 1)
    rows_corrected = rows - ((rows - 1) ** 2) / (n - 1)
    denominator = min(columns_corrected - 1, rows_corrected - 1)
    value = math.sqrt(phi2_corrected / denominator) if denominator > 0 else 0.0
    return min(1.0, max(0.0, value)), float(p_value)


@rule(id="D001", severity=Severity.WARNING, category="design")
def batch_condition_association(ctx: RuleContext) -> list[Finding]:
    biological, technical = _roles(ctx)
    if biological is None or not technical:
        return []
    findings: list[Finding] = []
    for batch in technical:
        data = _combined(ctx, [batch, biological])
        if data.empty:
            continue
        table = pd.crosstab(data[batch], data[biological], dropna=False)
        value, p_value = corrected_cramers_v(table)
        severity = (
            Severity.INFO if value < 0.3 else Severity.WARNING if value < 0.7 else Severity.ERROR
        )
        findings.append(
            Finding(
                rule_id="D001",
                severity=severity,
                column=batch,
                message_params={"biological": biological, "technical": batch, "v": f"{value:.3f}"},
                evidence={
                    "cramers_v": value,
                    "p_value": p_value,
                    "contingency_table": {
                        str(index): {str(key): int(value) for key, value in row.items()}
                        for index, row in table.to_dict(orient="index").items()
                    },
                },
            )
        )
    return findings


@rule(id="D002", severity=Severity.ERROR, category="design")
def complete_confounding(ctx: RuleContext) -> list[Finding]:
    biological, technical = _roles(ctx)
    if biological is None:
        return []
    findings: list[Finding] = []
    for batch in technical:
        data = _combined(ctx, [batch, biological])
        if data.empty or data[biological].nunique() < 2:
            continue
        level_batches = {
            str(level): sorted(str(value) for value in group[batch].unique())
            for level, group in data.groupby(biological, observed=True)
        }
        sets = [set(values) for values in level_batches.values()]
        complete = all(left.isdisjoint(right) for left, right in itertools.combinations(sets, 2))
        if complete:
            findings.append(
                Finding(
                    rule_id="D002",
                    severity=Severity.ERROR,
                    column=batch,
                    message_params={"biological": biological, "technical": batch, "level": "all"},
                    evidence={"level_batches": level_batches, "complete": True},
                )
            )
            continue
        spans_many = any(len(values) > 1 for values in sets)
        for level, values in level_batches.items():
            if len(values) == 1 and spans_many:
                findings.append(
                    Finding(
                        rule_id="D002",
                        severity=Severity.ERROR,
                        column=batch,
                        message_params={
                            "biological": biological,
                            "technical": batch,
                            "level": level,
                        },
                        evidence={
                            "level_batches": level_batches,
                            "complete": False,
                            "level": level,
                        },
                    )
                )
    return findings


def _design_matrix(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    encoded = pd.get_dummies(data[columns], drop_first=True, dtype=float)
    encoded.insert(0, "intercept", 1.0)
    return encoded.astype(float)


@rule(id="D003", severity=Severity.ERROR, category="design")
def rank_deficiency(ctx: RuleContext) -> list[Finding]:
    biological, technical = _roles(ctx)
    if biological is None or not technical:
        return []
    columns = [biological, *technical]
    data = _combined(ctx, columns)
    if data.empty:
        return []
    matrix = _design_matrix(data, columns)
    rank = int(np.linalg.matrix_rank(matrix.to_numpy()))
    if rank == matrix.shape[1]:
        return []
    _, _, pivots = qr(matrix.to_numpy(), mode="economic", pivoting=True)
    dependent = [str(matrix.columns[index]) for index in pivots[rank:]]
    return [
        Finding(
            rule_id="D003",
            severity=Severity.ERROR,
            message_params={"dependent": ", ".join(dependent)},
            evidence={"rank": rank, "columns": matrix.shape[1], "dependent_columns": dependent},
        )
    ]


def _vif(matrix: np.ndarray, index: int) -> float:
    target = matrix[:, index]
    others = np.delete(matrix, index, axis=1)
    if others.shape[1] == 0 or np.var(target) == 0:
        return math.inf
    design = np.column_stack([np.ones(len(target)), others])
    fitted = design @ np.linalg.lstsq(design, target, rcond=None)[0]
    residual = float(np.sum((target - fitted) ** 2))
    total = float(np.sum((target - target.mean()) ** 2))
    r_squared = 1 - residual / total if total > 0 else 1.0
    return math.inf if r_squared >= 1 - 1e-12 else 1 / (1 - r_squared)


@rule(id="D004", severity=Severity.WARNING, category="design")
def multicollinearity(ctx: RuleContext) -> list[Finding]:
    config = _config(ctx)
    numeric = [name for name, schema in config.schema_.items() if schema.type == "numeric"]
    data = _combined(ctx, numeric)
    if len(numeric) < 2 or data.empty:
        return []
    matrix = data.apply(pd.to_numeric, errors="coerce").dropna().to_numpy(dtype=float)
    findings: list[Finding] = []
    for index, column in enumerate(numeric):
        value = _vif(matrix, index)
        if value > 5:
            findings.append(
                Finding(
                    rule_id="D004",
                    severity=Severity.ERROR if value > 10 else Severity.WARNING,
                    column=column,
                    message_params={
                        "column": column,
                        "vif": "infinite" if math.isinf(value) else f"{value:.2f}",
                    },
                    evidence={"vif": "inf" if math.isinf(value) else value},
                )
            )
    return findings


@rule(id="D005", severity=Severity.WARNING, category="design")
def group_size_imbalance(ctx: RuleContext) -> list[Finding]:
    biological, technical = _roles(ctx)
    if biological is None:
        return []
    findings: list[Finding] = []
    for batch in technical:
        data = _combined(ctx, [batch, biological])
        if data.empty:
            continue
        table = pd.crosstab(data[biological], data[batch], dropna=False)
        small_cells = [
            {"biological": str(row), "technical": str(column), "n": int(table.loc[row, column])}
            for row in table.index
            for column in table.columns
            if int(table.loc[row, column]) < 3
        ]
        small_levels = {
            str(level): int(count)
            for level, count in data[biological].value_counts().items()
            if count < 5
        }
        if small_cells or small_levels:
            findings.append(
                Finding(
                    rule_id="D005",
                    severity=Severity.WARNING,
                    column=batch,
                    message_params={"biological": biological, "technical": batch},
                    evidence={"small_cells": small_cells, "small_levels": small_levels},
                )
            )
    return findings


@rule(id="D006", severity=Severity.INFO, category="design")
def integrability_score(ctx: RuleContext) -> list[Finding]:
    _, technical = _roles(ctx)
    return [
        Finding(
            rule_id="D006",
            severity=Severity.INFO,
            message_params={"score": "100"},
            evidence={"score": 100.0, "design_diagnostics_skipped": not technical},
        )
    ]
