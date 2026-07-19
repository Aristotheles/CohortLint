import pandas as pd

from cohortlint.config import CohortLintConfig
from cohortlint.model import RuleContext
from cohortlint.rules.units import (
    categorical_encoding_drift,
    decimal_separator_artifacts,
    numeric_unit_drift,
    out_of_range_values,
    scale_mismatch,
)


def _context(frames: dict[str, pd.DataFrame], schema: dict[str, object]) -> RuleContext:
    config = CohortLintConfig.model_validate(
        {
            "cohorts": [
                {"name": name, "path": f"{name}.csv", "sample_id": "id"} for name in frames
            ],
            "schema": schema,
        }
    )
    return RuleContext(
        cohorts=frames,
        merged=pd.concat(frames.values(), ignore_index=True, sort=False),
        config=config,
    )


def test_u001_identifies_age_in_months() -> None:
    ctx = _context(
        {
            "years": pd.DataFrame({"id": [1, 2, 3], "age": [20, 30, 40]}),
            "months": pd.DataFrame({"id": [4, 5, 6], "age": [240, 360, 480]}),
        },
        {"age": {"type": "numeric", "unit": "years"}},
    )
    finding = numeric_unit_drift(ctx)[0]
    assert finding.evidence["inferred_units"] == {"years": "years", "months": "months"}


def test_u002_reports_unmapped_with_nearest_match() -> None:
    ctx = _context(
        {"a": pd.DataFrame({"id": [1], "sex": ["femlae"]})},
        {"sex": {"type": "categorical", "allowed": ["female", "male"]}},
    )
    finding = categorical_encoding_drift(ctx)[0]
    assert finding.evidence["unmapped"]["a"]["femlae"] == "female"


def test_u003_detects_decimal_comma() -> None:
    ctx = _context(
        {"a": pd.DataFrame({"id": range(5), "value": ["1,1", "2,2", "3,3", "4,4", "5,5"]})},
        {"value": {"type": "numeric"}},
    )
    assert decimal_separator_artifacts(ctx)[0].evidence["fraction"] == 1


def test_u004_detects_spread_orders_of_magnitude() -> None:
    ctx = _context(
        {
            "a": pd.DataFrame({"id": range(4), "value": [1, 2, 3, 4]}),
            "b": pd.DataFrame({"id": range(4), "value": [1, 1001, 2001, 3001]}),
        },
        {"value": {"type": "numeric"}},
    )
    assert scale_mismatch(ctx)[0].rule_id == "U004"


def test_u005_reports_count_and_five_extremes() -> None:
    ctx = _context(
        {"a": pd.DataFrame({"id": range(7), "age": [-10, 20, 130, 140, 150, 160, 170]})},
        {"age": {"type": "numeric", "range": [0, 120]}},
    )
    finding = out_of_range_values(ctx)[0]
    assert finding.evidence["count"] == 6
    assert len(finding.evidence["extreme_values"]) == 5


def test_clean_units_do_not_trigger() -> None:
    ctx = _context(
        {
            "a": pd.DataFrame({"id": [1, 2], "age": [20, 30], "sex": ["f", "m"]}),
            "b": pd.DataFrame({"id": [3, 4], "age": [25, 35], "sex": ["f", "m"]}),
        },
        {
            "age": {"type": "numeric", "unit": "years", "range": [0, 120]},
            "sex": {"type": "categorical", "allowed": ["f", "m"]},
        },
    )
    assert numeric_unit_drift(ctx) == []
    assert categorical_encoding_drift(ctx) == []
    assert decimal_separator_artifacts(ctx) == []
    assert scale_mismatch(ctx) == []
    assert out_of_range_values(ctx) == []
