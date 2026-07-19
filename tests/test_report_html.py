from datetime import UTC, datetime

from cohortlint.model import Finding, Report, Severity
from cohortlint.report.html import render_html


def _report() -> Report:
    return Report(
        findings=[
            Finding(
                rule_id="S003",
                severity=Severity.WARNING,
                column="<script>alert(1)</script>",
                message_params={
                    "kind": "missing",
                    "column": "<script>alert(1)</script>",
                    "cohorts": "a",
                },
                evidence={"payload": "</pre><script>alert(2)</script>"},
            )
        ],
        cohorts=["a"],
        n_samples={"a": 1},
        integrability_score=88,
        generated_at=datetime.now(UTC),
        cohortlint_version="0.1.0",
    )


def test_html_escapes_metadata_and_has_restrictive_csp() -> None:
    html = render_html(_report(), "en")
    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
    assert "default-src &#39;none&#39;" in html or "default-src 'none'" in html


def test_html_renders_all_locales() -> None:
    for language, label in (("en", "Evidence"), ("de", "Evidenz"), ("tr", "Kanıt")):
        assert label in render_html(_report(), language)
