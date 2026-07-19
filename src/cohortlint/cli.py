"""Command-line interface."""

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Lint cohort metadata before omics integration.", no_args_is_help=True)


@app.command()
def init(output: Annotated[Path, typer.Option()] = Path("cohortlint.yaml")) -> None:
    """Create a CohortLint configuration file."""
    typer.echo(f"not implemented: would write {output}")


@app.command()
def check(paths: Annotated[list[Path] | None, typer.Argument()] = None) -> None:
    """Check one or more metadata tables."""
    del paths
    typer.echo("not implemented")


@app.command()
def harmonize(paths: Annotated[list[Path] | None, typer.Argument()] = None) -> None:
    """Apply only safe, declared metadata harmonizations."""
    del paths
    typer.echo("not implemented")


@app.command("rules")
def list_rules() -> None:
    """List available diagnostic rules."""
    typer.echo("not implemented")
