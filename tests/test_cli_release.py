import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from cohortlint.cli import app
from cohortlint.config import load_config


def test_init_writes_valid_config_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "cohortlint.yaml"
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--output", str(output)]).exit_code == 0
    load_config(output)
    original = output.read_bytes()
    assert runner.invoke(app, ["init", "--output", str(output)]).exit_code == 2
    assert output.read_bytes() == original


def test_rules_are_localized() -> None:
    result = CliRunner().invoke(app, ["rules", "--lang", "tr"])
    assert result.exit_code == 0
    assert "D002" in result.stdout
    assert "konfunding" in result.stdout


def test_python_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cohortlint", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Lint cohort metadata" in result.stdout


def test_generated_rule_document_covers_registry() -> None:
    from cohortlint import rules as _rules  # noqa: F401
    from cohortlint.registry import registered_rules

    documentation = Path("docs/rules.md").read_text(encoding="utf-8")
    assert all(f"| {definition.id} |" in documentation for definition in registered_rules())
