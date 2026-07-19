"""Generate docs/rules.md from the runtime rule registry."""

from pathlib import Path

from cohortlint import rules as _rules  # noqa: F401
from cohortlint.i18n import render
from cohortlint.registry import registered_rules


def main() -> None:
    lines = [
        "# CohortLint rule registry",
        "",
        "This file is generated from the registered runtime rules.",
        "",
        "| ID | Category | Default severity | English | Deutsch | Türkçe |",
        "|---|---|---|---|---|---|",
    ]
    for definition in registered_rules():
        titles = [render(definition.id, language, "title", {}) for language in ("en", "de", "tr")]
        escaped = [title.replace("|", "\\|") for title in titles]
        lines.append(
            f"| {definition.id} | {definition.category} | {definition.severity.value} | "
            f"{escaped[0]} | {escaped[1]} | {escaped[2]} |"
        )
    Path("docs/rules.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
