import pandas as pd

from cohortlint.config import CohortLintConfig
from cohortlint.model import RuleContext
from cohortlint.rules.privacy import (
    excessive_date_precision,
    k_anonymity_violation,
    residual_direct_identifiers,
)


def _context(frame: pd.DataFrame) -> RuleContext:
    config = CohortLintConfig.model_validate(
        {
            "cohorts": [{"name": "a", "path": "a.csv", "sample_id": "id"}],
            "schema": {
                "age": {"type": "numeric"},
                "sex": {"type": "categorical"},
                "condition": {"type": "categorical"},
            },
            "privacy": {"k_anonymity_threshold": 3},
        }
    )
    return RuleContext(cohorts={"a": frame}, merged=frame, config=config)


def test_p001_reports_counts_never_identifier_values() -> None:
    email = "private.person@example.org"
    frame = pd.DataFrame({"id": ["x"], "notes": [email], "location": ["10115"]})
    findings = residual_direct_identifiers(_context(frame))
    assert len(findings) == 2
    assert email not in str([finding.evidence for finding in findings])
    assert all("pattern_counts" in finding.evidence for finding in findings)


def test_p002_reports_only_group_sizes_and_drivers() -> None:
    frame = pd.DataFrame(
        {
            "id": range(4),
            "age": [20, 21, 40, 41],
            "sex": ["f", "f", "m", "m"],
            "condition": ["case", "case", "control", "control"],
        }
    )
    finding = k_anonymity_violation(_context(frame))[0]
    assert finding.evidence["group_sizes"] == [2, 2]
    assert "case" not in str(finding.evidence)


def test_p003_detects_day_precision() -> None:
    frame = pd.DataFrame({"id": [1, 2], "visit_date": ["2025-01-01", "2025-02-02"]})
    finding = excessive_date_precision(_context(frame))[0]
    assert finding.evidence["day_precision_fraction"] == 1


def test_privacy_clean_data_do_not_trigger() -> None:
    frame = pd.DataFrame(
        {
            "id": ["a", "b", "c"],
            "age": [20, 20, 20],
            "sex": ["f", "f", "f"],
            "condition": ["case", "case", "case"],
        }
    )
    ctx = _context(frame)
    assert residual_direct_identifiers(ctx) == []
    assert k_anonymity_violation(ctx) == []
    assert excessive_date_precision(ctx) == []
