import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from cohortlint.config import CohortLintConfig
from cohortlint.model import Finding, RuleContext, Severity
from cohortlint.registry import _integrability_score
from cohortlint.rules.design import (
    _vif,
    batch_condition_association,
    complete_confounding,
    corrected_cramers_v,
    group_size_imbalance,
    integrability_score,
    multicollinearity,
    rank_deficiency,
)


def _context(frame: pd.DataFrame, extra_schema: dict[str, object] | None = None) -> RuleContext:
    schema: dict[str, object] = {
        "condition": {"type": "categorical", "role": "biological"},
        "batch": {"type": "categorical", "role": "technical"},
    }
    schema.update(extra_schema or {})
    config = CohortLintConfig.model_validate(
        {
            "cohorts": [{"name": "study", "path": "study.csv", "sample_id": "id"}],
            "schema": schema,
        }
    )
    return RuleContext(cohorts={"study": frame}, merged=frame, config=config)


def test_corrected_cramers_v_golden_value() -> None:
    table = pd.DataFrame([[10, 0], [0, 10]])
    value, p_value = corrected_cramers_v(table)
    expected = math.sqrt((1 - 1 / 19) / (2 - 1 / 19 - 1))
    assert value == pytest.approx(expected, abs=1e-12)
    assert p_value < 0.001
    assert corrected_cramers_v(pd.DataFrame([[1, 2]])) == (0.0, 1.0)


@given(st.lists(st.integers(min_value=0, max_value=20), min_size=4, max_size=4))
def test_cramers_v_is_bounded(counts: list[int]) -> None:
    table = pd.DataFrame(np.array(counts).reshape(2, 2) + 1)
    value, _ = corrected_cramers_v(table)
    assert 0 <= value <= 1


def test_d001_balanced_design_is_info() -> None:
    frame = pd.DataFrame(
        {
            "id": range(20),
            "condition": ["case", "control"] * 10,
            "batch": ["a", "a", "b", "b"] * 5,
        }
    )
    finding = batch_condition_association(_context(frame))[0]
    assert finding.severity is Severity.INFO
    assert finding.evidence["cramers_v"] == 0


def test_d002_complete_confounding_accounts_for_levels() -> None:
    frame = pd.DataFrame(
        {
            "id": range(10),
            "condition": ["case"] * 5 + ["control"] * 5,
            "batch": ["a"] * 5 + ["b"] * 5,
        }
    )
    finding = complete_confounding(_context(frame))[0]
    assert finding.severity is Severity.ERROR
    assert finding.evidence["level_batches"] == {"case": ["a"], "control": ["b"]}


def test_d002_partial_confounding_scopes_level() -> None:
    frame = pd.DataFrame(
        {
            "id": range(9),
            "condition": ["case"] * 3 + ["control"] * 6,
            "batch": ["a"] * 3 + ["a"] * 3 + ["b"] * 3,
        }
    )
    finding = complete_confounding(_context(frame))[0]
    assert finding.evidence["complete"] is False
    assert finding.evidence["level"] == "case"


def test_d003_rank_deficiency_golden() -> None:
    frame = pd.DataFrame(
        {
            "id": range(8),
            "condition": ["case"] * 4 + ["control"] * 4,
            "batch": ["a"] * 4 + ["b"] * 4,
        }
    )
    finding = rank_deficiency(_context(frame))[0]
    assert finding.evidence["rank"] == 2
    assert finding.evidence["columns"] == 3
    assert len(finding.evidence["dependent_columns"]) == 1


def test_d003_full_rank_returns_clean() -> None:
    frame = pd.DataFrame(
        {
            "id": range(8),
            "condition": ["case", "control"] * 4,
            "batch": ["a", "a", "b", "b"] * 2,
        }
    )
    assert rank_deficiency(_context(frame)) == []


def test_d004_vif_golden_and_severity() -> None:
    x = np.arange(1, 21, dtype=float)
    assert _vif(np.column_stack([x, x * 2]), 0) == math.inf
    assert _vif(np.ones((4, 2)), 0) == math.inf
    frame = pd.DataFrame(
        {
            "id": range(20),
            "condition": ["case", "control"] * 10,
            "batch": ["a", "b"] * 10,
            "age": x,
            "score": x * 2,
        }
    )
    findings = multicollinearity(
        _context(frame, {"age": {"type": "numeric"}, "score": {"type": "numeric"}})
    )
    assert len(findings) == 2
    assert all(finding.severity is Severity.ERROR for finding in findings)


def test_d005_small_cells_and_levels() -> None:
    frame = pd.DataFrame(
        {
            "id": range(6),
            "condition": ["case"] * 2 + ["control"] * 4,
            "batch": ["a", "b", "a", "a", "b", "b"],
        }
    )
    finding = group_size_imbalance(_context(frame))[0]
    assert finding.evidence["small_cells"]
    assert finding.evidence["small_levels"] == {"case": 2, "control": 4}


def test_d006_penalties_and_no_technical_skip() -> None:
    findings = [
        Finding(rule_id="D002", severity=Severity.ERROR),
        Finding(rule_id="D003", severity=Severity.ERROR),
        Finding(rule_id="D001", severity=Severity.WARNING),
        Finding(rule_id="C001", severity=Severity.ERROR),
        Finding(rule_id="U001", severity=Severity.ERROR),
        Finding(rule_id="D005", severity=Severity.WARNING),
    ]
    assert _integrability_score(findings) == 9
    config = CohortLintConfig.model_validate(
        {
            "cohorts": [{"name": "a", "path": "a.csv", "sample_id": "id"}],
            "schema": {"condition": {"type": "categorical", "role": "biological"}},
        }
    )
    frame = pd.DataFrame({"id": [1], "condition": ["case"]})
    finding = integrability_score(RuleContext(cohorts={"a": frame}, merged=frame, config=config))[0]
    assert finding.evidence["design_diagnostics_skipped"] is True
