from pathlib import Path

import pandas as pd
from fixtures.synthetic.generate import generate_structural_fixture
from typer.testing import CliRunner

from cohortlint.cli import app
from cohortlint.config import CohortLintConfig
from cohortlint.model import RuleContext
from cohortlint.rules.structural import (
    observation_level_mixing,
    sample_identifier_integrity,
    schema_drift,
    type_disagreement,
)


def _context(frames: dict[str, pd.DataFrame], ratio: float = 1.5) -> RuleContext:
    config = CohortLintConfig.model_validate(
        {
            "version": 1,
            "cohorts": [
                {"name": name, "path": f"{name}.csv", "sample_id": "id"} for name in frames
            ],
            "schema": {"age": {"type": "numeric"}, "sex": {"type": "categorical"}},
            "rules": {"observation_level_ratio": ratio},
        }
    )
    merged = pd.concat(frames.values(), ignore_index=True, sort=False)
    return RuleContext(cohorts=frames, merged=merged, config=config)


def test_s001_reports_null_and_duplicate_row_indices() -> None:
    ctx = _context({"a": pd.DataFrame({"id": ["x", "x", None], "age": [1, 2, 3]})})
    findings = sample_identifier_integrity(ctx)
    assert {finding.message_params["problem"] for finding in findings} == {"null", "duplicate"}
    assert {tuple(finding.evidence["row_indices"]) for finding in findings} == {(2,), (0, 1)}


def test_s001_clean_identifiers_do_not_trigger() -> None:
    ctx = _context({"a": pd.DataFrame({"id": ["x", "y"], "age": [1, 2]})})
    assert sample_identifier_integrity(ctx) == []


def test_s002_detects_cell_level_ratio() -> None:
    frame = pd.DataFrame({"id": ["x", "x", "x", "y"], "age": [1, 1, 1, 2]})
    findings = observation_level_mixing(_context({"a": frame}))
    assert findings[0].rule_id == "S002"
    assert findings[0].evidence["ratio"] == 2


def test_s003_reports_missing_and_extra_columns() -> None:
    ctx = _context(
        {
            "a": pd.DataFrame({"id": ["a"], "age": [20], "site": ["x"]}),
            "b": pd.DataFrame({"id": ["b"], "age": [30], "sex": ["f"]}),
        }
    )
    findings = schema_drift(ctx)
    assert any(f.column == "sex" and f.evidence["missing_cohorts"] == ["a"] for f in findings)
    assert any(f.evidence.get("extra_columns") == {"a": ["site"]} for f in findings)


def test_s004_reports_blocking_values_only_for_disagreement() -> None:
    ctx = _context(
        {
            "a": pd.DataFrame({"id": ["a"], "age": [20], "sex": ["f"]}),
            "b": pd.DataFrame({"id": ["b", "c"], "age": ["unknown", "30"], "sex": ["m", "f"]}),
        }
    )
    findings = type_disagreement(ctx)
    assert len(findings) == 1
    assert findings[0].evidence["offending_values"] == {"b": ["unknown"]}


def test_cli_check_clean_fixture(tmp_path: Path) -> None:
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    pd.DataFrame({"id": ["a"], "age": [20], "sex": ["f"]}).to_csv(first, index=False)
    pd.DataFrame({"id": ["b"], "age": [30], "sex": ["m"]}).to_csv(second, index=False)
    config = tmp_path / "cohortlint.yaml"
    config.write_text(
        f"""version: 1
cohorts:
  - {{name: a, path: '{first.as_posix()}', sample_id: id}}
  - {{name: b, path: '{second.as_posix()}', sample_id: id}}
schema:
  age: {{type: numeric}}
  sex: {{type: categorical}}
""",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["check", "--config", str(config)])
    assert result.exit_code == 0
    assert result.stdout.strip() == "No findings."


def test_cli_reports_exact_structural_fixture_findings(tmp_path: Path) -> None:
    config = generate_structural_fixture(tmp_path)
    result = CliRunner().invoke(app, ["check", "--config", str(config)])
    assert result.exit_code == 1
    reported = [
        line.split("]", 1)[0][1:] for line in result.stdout.splitlines() if line.startswith("[")
    ]
    assert reported == [
        "S001",
        "S004",
        "S002",
        "S003",
    ]
