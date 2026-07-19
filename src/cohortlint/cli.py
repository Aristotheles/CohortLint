"""Command-line interface."""

from pathlib import Path
from typing import Annotated

import typer

from cohortlint import rules as _rules  # noqa: F401
from cohortlint.config import load_config
from cohortlint.i18n import resolve_language
from cohortlint.loader import load_metadata
from cohortlint.model import RuleContext, Severity
from cohortlint.registry import registered_rules, run_rules
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
        typer.echo(render_terminal(findings, language))
    except (ValueError, OSError) as exc:
        typer.echo(f"Execution error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if any(finding.severity is Severity.ERROR for finding in findings):
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
