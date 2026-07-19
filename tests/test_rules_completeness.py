import pandas as pd

from cohortlint.config import CohortLintConfig
from cohortlint.model import RuleContext
from cohortlint.rules.completeness import (
    differential_missingness,
    high_missingness,
    required_covariate_absent,
)


def _context(frame: pd.DataFrame) -> RuleContext:
    config = CohortLintConfig.model_validate(
        {
            "cohorts": [{"name": "a", "path": "a.csv", "sample_id": "id"}],
            "schema": {
                "condition": {"type": "categorical", "role": "biological", "required": True},
                "age": {"type": "numeric", "required": True},
            },
        }
    )
    return RuleContext(cohorts={"a": frame}, merged=frame, config=config)


def test_c001_required_covariate_absent() -> None:
    findings = required_covariate_absent(_context(pd.DataFrame({"id": [1], "condition": ["x"]})))
    assert [(finding.rule_id, finding.column) for finding in findings] == [("C001", "age")]


def test_c002_high_missingness() -> None:
    frame = pd.DataFrame({"id": range(5), "condition": ["a"] * 5, "age": [1, None, None, 4, 5]})
    finding = high_missingness(_context(frame))[0]
    assert finding.evidence["fraction"] == 0.4


def test_c003_detects_biological_association_after_bh() -> None:
    condition = ["case"] * 50 + ["control"] * 50
    age = [None] * 45 + [30] * 5 + [30] * 50
    findings = differential_missingness(
        _context(pd.DataFrame({"id": range(100), "condition": condition, "age": age}))
    )
    assert len(findings) == 1
    assert findings[0].evidence["q_value"] < 0.05


def test_completeness_clean_data_do_not_trigger() -> None:
    frame = pd.DataFrame({"id": range(4), "condition": ["a", "b", "a", "b"], "age": [1, 2, 3, 4]})
    ctx = _context(frame)
    assert required_covariate_absent(ctx) == []
    assert high_missingness(ctx) == []
    assert differential_missingness(ctx) == []
