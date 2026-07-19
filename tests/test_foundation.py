from datetime import UTC, datetime

import pandas as pd
import pytest
from typer.testing import CliRunner

import cohortlint.registry as registry
from cohortlint.cli import app
from cohortlint.i18n import catalogue, render, resolve_language
from cohortlint.model import Finding, Report, RuleContext, Severity
from cohortlint.registry import rule, run_rules


def test_report_model() -> None:
    finding = Finding(rule_id="T999", severity=Severity.INFO)
    report = Report(
        findings=[finding],
        cohorts=["a"],
        n_samples={"a": 1},
        integrability_score=100,
        generated_at=datetime.now(UTC),
        cohortlint_version="0.1.0",
    )
    assert report.findings[0].severity is Severity.INFO


def test_registry_executes_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "_RULES", {})
    rule_id = "T_FOUNDATION"

    @rule(id=rule_id, severity=Severity.INFO, category="test")
    def example(ctx: RuleContext) -> list[Finding]:
        del ctx
        return [Finding(rule_id=rule_id, severity=Severity.INFO)]

    frame = pd.DataFrame({"sample": ["x"]})
    context = RuleContext(cohorts={"a": frame}, merged=frame, config={})
    assert any(item.rule_id == rule_id for item in run_rules(context))


def test_locale_key_parity_and_rendering() -> None:
    keys = [set(catalogue(language)) for language in ("en", "de", "tr")]
    assert keys[0] == keys[1] == keys[2]
    assert render("TEST001", "tr", "detail", {"name": "örnek"}) == "örnek için test ayrıntısı"


def test_language_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHORTLINT_LANG", "tr")
    assert resolve_language() == "tr"
    assert resolve_language(config_language="de") == "de"
    assert resolve_language("en", "de") == "en"


def test_cli_help_and_skeleton_commands() -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    for command in ("init", "harmonize"):
        result = runner.invoke(app, [command])
        assert result.exit_code == 0
        assert "not implemented" in result.stdout
    rules_result = runner.invoke(app, ["rules"])
    assert rules_result.exit_code == 0
    assert "S001" in rules_result.stdout
