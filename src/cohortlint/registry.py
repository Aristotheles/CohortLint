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
    return findings
