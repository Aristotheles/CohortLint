"""Escaped, self-contained HTML report rendering."""

from __future__ import annotations

import json
from collections import defaultdict
from importlib.resources import files

from jinja2 import Environment, StrictUndefined, select_autoescape

from cohortlint.i18n import catalogue, render
from cohortlint.model import Report


def render_html(report: Report, language: str) -> str:
    template_text = (
        files("cohortlint.report.templates").joinpath("report.html.j2").read_text(encoding="utf-8")
    )
    environment = Environment(
        autoescape=select_autoescape(default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.from_string(template_text)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for finding in report.findings:
        grouped[finding.rule_id[0]].append(
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity.value,
                "scope": "/".join(value for value in (finding.cohort, finding.column) if value)
                or "all",
                "title": render(finding.rule_id, language, "title", finding.message_params),
                "detail": render(finding.rule_id, language, "detail", finding.message_params),
                "suggestion": render(
                    finding.rule_id, language, "suggestion", finding.suggestion_params
                ),
                "evidence": json.dumps(finding.evidence, ensure_ascii=False, indent=2),
            }
        )
    return template.render(
        report=report,
        grouped=dict(sorted(grouped.items())),
        language=language,
        labels=catalogue(language)["REPORT"],
    )
