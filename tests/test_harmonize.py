import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from cohortlint.cli import app
from cohortlint.config import CohortLintConfig
from cohortlint.harmonize import harmonize_metadata, write_harmonized
from cohortlint.model import RuleContext
from cohortlint.rules.vocabulary import (
    low_confidence_mappings,
    near_duplicate_labels,
    unmapped_ontology_terms,
)


def _write_cache(base: Path) -> None:
    cache = base / ".cohortlint_cache"
    cache.mkdir()
    (cache / "UBERON.json").write_text(
        json.dumps(
            {
                "ontology_version": "UBERON",
                "mappings": {
                    "PBMC": {
                        "subject_label": "PBMC",
                        "object_id": "CL:2000001",
                        "object_label": "peripheral blood mononuclear cell",
                        "confidence": 0.99,
                    },
                    "pbmcs": {
                        "subject_label": "pbmcs",
                        "object_id": "CL:2000001",
                        "object_label": "peripheral blood mononuclear cell",
                        "confidence": 0.99,
                    },
                    "peripheral blood mononuclear cell": {
                        "subject_label": "peripheral blood mononuclear cell",
                        "object_id": "CL:2000001",
                        "object_label": "peripheral blood mononuclear cell",
                        "confidence": 0.90,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _config(path: Path) -> CohortLintConfig:
    return CohortLintConfig.model_validate(
        {
            "cohorts": [{"name": "a", "path": path, "sample_id": "id"}],
            "schema": {
                "sex": {
                    "type": "categorical",
                    "allowed": ["female", "male"],
                    "synonyms": {"female": ["F"]},
                },
                "value": {"type": "numeric"},
                "tissue": {"type": "ontology", "ontology": "UBERON"},
            },
        }
    )


def test_vocabulary_rules_use_offline_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_cache(tmp_path)
    frame = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "sex": ["F", "female", "male"],
            "value": [1, 2, 3],
            "tissue": ["PBMC", "pbmcs", "peripheral blood mononuclear cell"],
        }
    )
    ctx = RuleContext(cohorts={"a": frame}, merged=frame, config=_config(tmp_path / "meta.csv"))
    assert unmapped_ontology_terms(ctx) == []
    assert len(low_confidence_mappings(ctx)) == 1
    duplicate = near_duplicate_labels(ctx)[0]
    assert duplicate.evidence["duplicates"]["CL:2000001"] == [
        "PBMC",
        "pbmcs",
        "peripheral blood mononuclear cell",
    ]


def test_harmonize_safe_rules_and_sssom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_cache(tmp_path)
    source = tmp_path / "meta.csv"
    pd.DataFrame(
        {
            "id": [1, 2],
            "sex": ["F", "male"],
            "value": ["1,5", "2,5"],
            "tissue": ["PBMC", "pbmcs"],
        }
    ).to_csv(source, index=False)
    frame, provenance, sssom = harmonize_metadata(_config(source))
    assert frame["sex"].tolist() == ["female", "male"]
    assert frame["value"].tolist() == [1.5, 2.5]
    assert frame["tissue"].tolist() == ["CL:2000001", "CL:2000001"]
    assert {item["rule_id"] for item in provenance} == {"U002", "U003", "V003"}
    output = tmp_path / "merged.csv"
    mappings = tmp_path / "mappings.sssom.tsv"
    write_harmonized(frame, provenance, sssom, output, mappings)
    assert output.exists()
    assert output.with_suffix(".csv.provenance.json").exists()
    assert mappings.read_text(encoding="utf-8").splitlines()[0].split("\t") == [
        "subject_id",
        "subject_label",
        "predicate_id",
        "object_id",
        "object_label",
        "mapping_justification",
        "confidence",
    ]


def test_harmonize_cli_dry_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "meta.csv"
    pd.DataFrame({"id": [1], "sex": ["F"], "value": ["1,5"], "tissue": [None]}).to_csv(
        source, index=False
    )
    config = tmp_path / "cohortlint.yaml"
    config.write_text(
        f"""version: 1
cohorts:
  - {{name: a, path: '{source.as_posix()}', sample_id: id}}
schema:
  sex: {{type: categorical, allowed: [female], synonyms: {{female: [F]}}}}
  value: {{type: numeric}}
  tissue: {{type: ontology, ontology: UBERON}}
""",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["harmonize", "--config", str(config), "--dry-run"])
    assert result.exit_code == 0
    assert not (tmp_path / "merged.csv").exists()
