"""Rule registration and execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cohortlint.model import Finding, RuleContext, Severity

RuleFn = Callable[[RuleContext], list[Finding]]


@dataclass(frozen=True)
class RuleDefinition:
    id: str
    severity: Severity
    category: str
    function: RuleFn


_RULES: dict[str, RuleDefinition] = {}


def rule(*, id: str, severity: Severity, category: str) -> Callable[[RuleFn], RuleFn]:
    """Register a rule while leaving the decorated function directly callable."""

    def decorator(function: RuleFn) -> RuleFn:
        if id in _RULES:
            raise ValueError(f"Duplicate rule id: {id}")
        _RULES[id] = RuleDefinition(id, severity, category, function)
        return function

    return decorator


def registered_rules() -> tuple[RuleDefinition, ...]:
    return tuple(_RULES[key] for key in sorted(_RULES))


def run_rules(ctx: RuleContext, disabled: set[str] | None = None) -> list[Finding]:
    disabled = disabled or set()
    findings: list[Finding] = []
    for definition in registered_rules():
        if definition.id not in disabled:
            findings.extend(definition.function(ctx))
    for index, finding in enumerate(findings):
        if finding.rule_id == "D006":
            score = _integrability_score(findings)
            findings[index] = finding.model_copy(
                update={
                    "message_params": {"score": f"{score:.0f}"},
                    "evidence": {"score": score},
                }
            )
    return findings


def _integrability_score(findings: list[Finding]) -> float:
    """Compute the specified communication heuristic; this is not a statistic."""

    score = 100.0
    if any(finding.rule_id == "D002" for finding in findings):
        score -= 40
    if any(finding.rule_id == "D003" for finding in findings):
        score -= 25
    score -= 15 * sum(
        finding.rule_id == "D001" and finding.severity is Severity.ERROR for finding in findings
    )
    score -= 8 * sum(
        finding.rule_id == "D001" and finding.severity is Severity.WARNING for finding in findings
    )
    score -= 10 * sum(finding.rule_id == "C001" for finding in findings)
    score -= 5 * sum(finding.rule_id == "U001" for finding in findings)
    score -= 3 * sum(finding.rule_id == "D005" for finding in findings)
    return max(0.0, score)
