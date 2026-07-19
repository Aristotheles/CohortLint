from pathlib import Path

import pandas as pd
import pytest

from cohortlint.config import CohortConfig, load_config
from cohortlint.loader import load_metadata, read_table


def _write_config(path: Path) -> None:
    path.write_text(
        """version: 1
cohorts:
  - name: csv
    path: data/a.csv
    sample_id: id
  - name: tsv
    path: data/b.tsv
    sample_id: id
schema:
  age:
    type: numeric
    required: true
""",
        encoding="utf-8",
    )


def test_config_resolves_relative_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "cohortlint.yaml"
    _write_config(config_path)
    config = load_config(config_path)
    assert config.cohorts[0].path == tmp_path / "data/a.csv"
    assert config.schema_["age"].required


def test_csv_tsv_and_merge_loading(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame({"id": ["a1"], "age": [20]}).to_csv(data / "a.csv", index=False)
    pd.DataFrame({"id": ["b1"], "age": [30]}).to_csv(data / "b.tsv", sep="\t", index=False)
    config_path = tmp_path / "cohortlint.yaml"
    _write_config(config_path)
    loaded = load_metadata(load_config(config_path))
    assert list(loaded.cohorts) == ["csv", "tsv"]
    assert loaded.merged["__sample_id__"].tolist() == ["csv:a1", "tsv:b1"]


def test_xlsx_loading(tmp_path: Path) -> None:
    path = tmp_path / "metadata.xlsx"
    pd.DataFrame({"id": [1], "age": [42]}).to_excel(path, sheet_name="metadata", index=False)
    frame = read_table(CohortConfig(name="excel", path=path, sample_id="id", sheet="metadata"))
    assert frame.loc[0, "age"] == 42


def test_unsupported_format_is_execution_error(tmp_path: Path) -> None:
    path = tmp_path / "metadata.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported metadata format"):
        read_table(CohortConfig(name="bad", path=path, sample_id="id"))
