"""Locale catalogue loading and message rendering."""

from __future__ import annotations

import os
from importlib.resources import files
from typing import Any

import yaml

SUPPORTED_LANGUAGES = ("en", "de", "tr")


def resolve_language(flag: str | None = None, config_language: str | None = None) -> str:
    language = flag or config_language or os.getenv("COHORTLINT_LANG") or "en"
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    return language


def catalogue(language: str) -> dict[str, dict[str, str]]:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {language}")
    resource = files("cohortlint.locales").joinpath(f"{language}.yaml")
    loaded = yaml.safe_load(resource.read_text(encoding="utf-8"))
    return dict(loaded)


def render(rule_id: str, language: str, field: str, params: dict[str, Any]) -> str:
    try:
        template = catalogue(language)[rule_id][field]
    except KeyError as exc:
        raise KeyError(f"Missing locale entry: {language}.{rule_id}.{field}") from exc
    return template.format(**params)
