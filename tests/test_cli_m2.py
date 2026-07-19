import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from cohortlint.cli import app


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "meta.csv"
    pd.DataFrame({"id": ["a", "b"], "age": [20, 30]}).to_csv(source, index=False)
    config = tmp_path / "cohortlint.yaml"
    config.write_text(
        f"""version: 1
cohorts:
  - {{name: a, path: '{source.as_posix()}', sample_id: id}}
schema:
  age: {{type: numeric, range: [0, 120]}}
""",
        encoding="utf-8",
    )
    return config, source


def test_json_report_contract(tmp_path: Path) -> None:
    config, _ = _fixture(tmp_path)
    result = CliRunner().invoke(app, ["check", "--config", str(config), "--format", "json"])
    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["cohorts"] == ["a"]
    assert report["n_samples"] == {"a": 2}
    assert report["integrability_score"] == 100


def test_output_cannot_overwrite_input(tmp_path: Path) -> None:
    config, source = _fixture(tmp_path)
    original = source.read_bytes()
    result = CliRunner().invoke(
        app,
        ["check", "--config", str(config), "--format", "json", "--output", str(source)],
    )
    assert result.exit_code == 2
    assert source.read_bytes() == original
