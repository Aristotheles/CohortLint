"""Command-line interface."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from cohortlint import __version__
from cohortlint import rules as _rules  # noqa: F401
from cohortlint.config import load_config
from cohortlint.i18n import resolve_language
from cohortlint.loader import load_metadata
from cohortlint.model import Report, RuleContext, Severity
from cohortlint.registry import registered_rules, run_rules
from cohortlint.report.json import render_json
from cohortlint.report.terminal import render_terminal

app = typer.Typer(help="Lint cohort metadata before omics integration.", no_args_is_help=True)


@app.command()
def init(output: Annotated[Path, typer.Option()] = Path("cohortlint.yaml")) -> None:
    """Create a CohortLint configuration file."""
    typer.echo(f"not implemented: would write {output}")


@app.command()
def check(
    paths: Annotated[list[Path] | None, typer.Argument()] = None,
    config_path: Annotated[Path, typer.Option("--config")] = Path("cohortlint.yaml"),
    lang: Annotated[str | None, typer.Option("--lang")] = None,
    format_: Annotated[str, typer.Option("--format")] = "terminal",
    output: Annotated[Path | None, typer.Option("--output")] = None,
    fail_on: Annotated[str, typer.Option("--fail-on")] = "error",
    disable: Annotated[list[str] | None, typer.Option("--disable")] = None,
) -> None:
    """Check one or more metadata tables."""
    try:
        config = load_config(config_path)
        if paths:
            if len(paths) != len(config.cohorts):
                raise ValueError("PATHS count must match the configured cohort count")
            config = config.model_copy(
                update={
                    "cohorts": [
                        cohort.model_copy(update={"path": path.resolve()})
                        for cohort, path in zip(config.cohorts, paths, strict=True)
                    ]
                }
            )
        loaded = load_metadata(config)
        context = RuleContext(cohorts=loaded.cohorts, merged=loaded.merged, config=config)
        disabled = set(config.rules.disable) | set(disable or [])
        findings = run_rules(context, disabled)
        overrides = config.rules.severity_overrides
        findings = [
            finding.model_copy(update={"severity": Severity(overrides[finding.rule_id])})
            if finding.rule_id in overrides
            else finding
            for finding in findings
        ]
        language = resolve_language(lang, config.output.lang)
        if format_ not in {"terminal", "json"}:
            raise ValueError("--format must be terminal or json")
        if fail_on not in {"error", "warning", "never"}:
            raise ValueError("--fail-on must be error, warning, or never")
        report = Report(
            findings=findings,
            cohorts=list(loaded.cohorts),
            n_samples={name: len(frame) for name, frame in loaded.cohorts.items()},
            integrability_score=100,
            generated_at=datetime.now(UTC),
            cohortlint_version=__version__,
        )
        rendered = render_json(report) if format_ == "json" else render_terminal(findings, language)
        if output is None:
            typer.echo(rendered)
        else:
            protected = {
                config_path.resolve(),
                *(cohort.path.resolve() for cohort in config.cohorts),
            }
            if output.resolve() in protected:
                raise ValueError("output path must not overwrite config or cohort input files")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        typer.echo(f"Execution error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    should_fail = fail_on != "never" and any(
        finding.severity is Severity.ERROR
        or (fail_on == "warning" and finding.severity is Severity.WARNING)
        for finding in findings
    )
    if should_fail:
        raise typer.Exit(code=1)


@app.command()
def harmonize(paths: Annotated[list[Path] | None, typer.Argument()] = None) -> None:
    """Apply only safe, declared metadata harmonizations."""
    del paths
    typer.echo("not implemented")


@app.command("rules")
def list_rules() -> None:
    """List available diagnostic rules."""
    for definition in registered_rules():
        typer.echo(f"{definition.id}\t{definition.category}\t{definition.severity.value}")
