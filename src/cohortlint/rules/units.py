"""Unit and encoding rules U001-U005."""

from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd

from cohortlint.config import CohortLintConfig, SchemaColumn
from cohortlint.model import Finding, RuleContext, Severity
from cohortlint.registry import rule

_DECIMAL_COMMA = re.compile(r"^-?\d+,\d+$")


def _config(ctx: RuleContext) -> CohortLintConfig:
    return (
        ctx.config
        if isinstance(ctx.config, CohortLintConfig)
        else CohortLintConfig.model_validate(ctx.config)
    )


def _numeric_by_cohort(ctx: RuleContext, column: str) -> dict[str, pd.Series[Any]]:
    result: dict[str, pd.Series[Any]] = {}
    for name, frame in ctx.cohorts.items():
        if column in frame:
            values = pd.to_numeric(frame[column], errors="coerce").dropna()
            if not values.empty:
                result[name] = values
    return result


def _infer_age_unit(values: pd.Series[Any]) -> str:
    median = float(values.median())
    integer_fraction = float(np.isclose(values % 1, 0).mean())
    if 1900 <= median <= 2026:
        return "birth_year"
    if 12 <= median <= 1440 and integer_fraction >= 0.9 and median > 120:
        return "months"
    if 0 <= median <= 3:
        return "decades_or_error"
    if 0 <= median <= 120:
        return "years"
    return "unknown"


@rule(id="U001", severity=Severity.ERROR, category="units")
def numeric_unit_drift(ctx: RuleContext) -> list[Finding]:
    config = _config(ctx)
    findings: list[Finding] = []
    for column, schema in config.schema_.items():
        if schema.type != "numeric":
            continue
        values = _numeric_by_cohort(ctx, column)
        if len(values) < 2:
            continue
        medians = {name: float(series.median()) for name, series in values.items()}
        positive = [abs(value) for value in medians.values() if value != 0 and math.isfinite(value)]
        ratio = max(positive) / min(positive) if len(positive) >= 2 else 1.0
        inferred = (
            {name: _infer_age_unit(series) for name, series in values.items()}
            if column.casefold() == "age"
            else {name: "unknown" for name in values}
        )
        age_disagreement = column.casefold() == "age" and len(set(inferred.values())) > 1
        if ratio > config.rules.unit_median_ratio or age_disagreement:
            findings.append(
                Finding(
                    rule_id="U001",
                    severity=Severity.ERROR,
                    column=column,
                    message_params={
                        "column": column,
                        "declared_unit": schema.unit or "unspecified",
                    },
                    evidence={"medians": medians, "ratio": ratio, "inferred_units": inferred},
                )
            )
    return findings


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for index, char_left in enumerate(left, start=1):
        current = [index]
        for other_index, char_right in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other_index] + 1,
                    previous[other_index - 1] + (char_left != char_right),
                )
            )
        previous = current
    return previous[-1]


def _known_values(schema: SchemaColumn) -> list[str]:
    return [str(value) for value in schema.allowed] + [
        str(value) for values in schema.synonyms.values() for value in values
    ]


@rule(id="U002", severity=Severity.WARNING, category="units")
def categorical_encoding_drift(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for column, schema in _config(ctx).schema_.items():
        if schema.type != "categorical":
            continue
        known = _known_values(schema)
        if not known:
            continue
        known_folded = {value.casefold() for value in known}
        allowed_folded = {str(value).casefold() for value in schema.allowed}
        unmapped: dict[str, dict[str, str | None]] = {}
        for name, frame in ctx.cohorts.items():
            if column not in frame:
                continue
            for raw in frame[column].dropna().astype(str).drop_duplicates():
                folded = raw.casefold()
                if folded in known_folded or folded in allowed_folded:
                    continue
                candidates = [
                    value for value in known if _levenshtein(folded, value.casefold()) <= 2
                ]
                unmapped.setdefault(name, {})[raw] = (
                    min(candidates, key=len) if candidates else None
                )
        if unmapped:
            findings.append(
                Finding(
                    rule_id="U002",
                    severity=Severity.WARNING,
                    column=column,
                    message_params={"column": column},
                    evidence={"unmapped": unmapped},
                )
            )
    return findings


@rule(id="U003", severity=Severity.ERROR, category="units")
def decimal_separator_artifacts(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    config = _config(ctx)
    for column, schema in config.schema_.items():
        if schema.type != "numeric":
            continue
        for name, frame in ctx.cohorts.items():
            if column not in frame:
                continue
            values = frame[column].dropna().astype(str)
            if values.empty:
                continue
            fraction = float(values.str.fullmatch(_DECIMAL_COMMA).mean())
            if fraction > config.rules.decimal_separator_fraction:
                findings.append(
                    Finding(
                        rule_id="U003",
                        severity=Severity.ERROR,
                        cohort=name,
                        column=column,
                        message_params={"column": column, "fraction": f"{fraction:.1%}"},
                        evidence={"fraction": fraction, "count": int(len(values))},
                    )
                )
    return findings


@rule(id="U004", severity=Severity.WARNING, category="units")
def scale_mismatch(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    config = _config(ctx)
    for column, schema in config.schema_.items():
        if schema.type != "numeric":
            continue
        values = _numeric_by_cohort(ctx, column)
        iqrs = {
            name: float(series.quantile(0.75) - series.quantile(0.25))
            for name, series in values.items()
        }
        positive = [value for value in iqrs.values() if value > 0]
        if (
            len(positive) >= 2
            and math.log10(max(positive) / min(positive)) > config.rules.scale_iqr_orders
        ):
            findings.append(
                Finding(
                    rule_id="U004",
                    severity=Severity.WARNING,
                    column=column,
                    message_params={"column": column},
                    evidence={"iqr": iqrs},
                )
            )
    return findings


def _extreme_values(values: pd.Series[Any], low: float, high: float) -> list[float]:
    outside = values[(values < low) | (values > high)]
    ranked = sorted(
        (float(value) for value in outside),
        key=lambda value: max(low - value, value - high),
        reverse=True,
    )
    return ranked[:5]


@rule(id="U005", severity=Severity.WARNING, category="units")
def out_of_range_values(ctx: RuleContext) -> list[Finding]:
    findings: list[Finding] = []
    for column, schema in _config(ctx).schema_.items():
        if schema.type != "numeric" or schema.range is None:
            continue
        low, high = schema.range
        for name, values in _numeric_by_cohort(ctx, column).items():
            extremes = _extreme_values(values, low, high)
            count = int(((values < low) | (values > high)).sum())
            if count:
                findings.append(
                    Finding(
                        rule_id="U005",
                        severity=Severity.WARNING,
                        cohort=name,
                        column=column,
                        message_params={"column": column, "count": count},
                        evidence={"count": count, "extreme_values": extremes, "range": [low, high]},
                    )
                )
    return findings
