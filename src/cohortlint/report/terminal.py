"""Plain-text terminal reporter."""

from __future__ import annotations

from cohortlint.i18n import render
from cohortlint.model import Finding, Severity

_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


def render_terminal(findings: list[Finding], language: str) -> str:
    if not findings:
        return "No findings."
    lines: list[str] = []
    current: Severity | None = None
    for finding in sorted(findings, key=lambda item: (_ORDER[item.severity], item.rule_id)):
        if finding.severity is not current:
            current = finding.severity
            if lines:
                lines.append("")
            lines.append(current.value.upper())
        scope = "/".join(value for value in (finding.cohort, finding.column) if value) or "all"
        detail = render(finding.rule_id, language, "detail", finding.message_params)
        suggestion = render(finding.rule_id, language, "suggestion", finding.suggestion_params)
        lines.append(f"[{finding.rule_id}] {scope}: {detail}")
        lines.append(f"  -> {suggestion}")
    return "\n".join(lines)
