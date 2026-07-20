"""Reproducible public-data transcriptomics case study for GSE171524."""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import gzip
import html
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from scipy import stats

from cohortlint import __version__
from cohortlint import rules as _rules  # noqa: F401
from cohortlint.config import load_config
from cohortlint.i18n import resolve_language
from cohortlint.loader import load_metadata
from cohortlint.model import Report, RuleContext, Severity
from cohortlint.registry import run_rules
from cohortlint.report.html import render_html
from cohortlint.report.json import render_json

CASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = CASE_DIR / "data"
DEFAULT_RESULTS_DIR = CASE_DIR / "results"

GEO_ACCESSION = "GSE171524"
METADATA_URL = (
    "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE171nnn/"
    "GSE171524/suppl/GSE171524_lung_metaData.txt.gz"
)
RAW_ARCHIVE_URL = (
    "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE171nnn/GSE171524/suppl/GSE171524_RAW.tar"
)
EXPECTED_ARCHIVE_BYTES = 169_728_000
MAX_DOWNLOAD_BYTES = 220_000_000
TRUSTED_DOWNLOAD_HOST = "ftp.ncbi.nlm.nih.gov"


@dataclass(frozen=True)
class Library:
    accession: str
    donor: str
    condition: str

    @property
    def filename(self) -> str:
        return f"{self.accession}_{self.donor}_raw_counts.csv.gz"


LIBRARIES = (
    Library("GSM5226574", "C51ctr", "Control"),
    Library("GSM5226575", "C52ctr", "Control"),
    Library("GSM5226576", "C53ctr", "Control"),
    Library("GSM5226577", "C54ctr", "Control"),
    Library("GSM5226578", "C55ctr", "Control"),
    Library("GSM5226579", "C56ctr", "Control"),
    Library("GSM5226580", "C57ctr", "Control"),
    Library("GSM5226581", "L01cov", "COVID-19"),
    Library("GSM5226582", "L03cov", "COVID-19"),
    Library("GSM5226583", "L04cov", "COVID-19"),
    Library("GSM5226584", "L04covaddon", "COVID-19"),
    Library("GSM5226585", "L05cov", "COVID-19"),
    Library("GSM5226586", "L06cov", "COVID-19"),
    Library("GSM5226587", "L07cov", "COVID-19"),
)

DONOR_ALIASES = {"L04covaddon": "L04cov"}
DISCOVERY_DONORS = {"C51ctr", "C53ctr", "C55ctr", "C57ctr", "L03cov", "L05cov", "L07cov"}
MARKER_GENES = (
    "ISG15",
    "IFIT1",
    "IFIT3",
    "IFITM3",
    "MX1",
    "OAS1",
    "CXCL10",
    "STAT1",
    "IL6",
    "ACE2",
)


def validate_download_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != TRUSTED_DOWNLOAD_HOST:
        raise ValueError(f"Refusing untrusted download URL: {url}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Download URL must not contain credentials")


def download_bounded(url: str, destination: Path, *, expected_bytes: int | None = None) -> None:
    """Download over HTTPS with a size cap and atomic final rename."""
    validate_download_url(url)
    if destination.exists() and (
        expected_bytes is None or destination.stat().st_size == expected_bytes
    ):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "CohortLint-case-study/1.0"})
    # The scheme and host are allowlisted before opening and again after redirects.
    with (
        urllib.request.urlopen(  # nosec B310
            request, timeout=60
        ) as response,
        partial.open("wb") as output,
    ):
        validate_download_url(response.geturl())
        declared = response.headers.get("Content-Length")
        if declared is not None and int(declared) > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"Refusing download larger than {MAX_DOWNLOAD_BYTES} bytes")
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError("Download exceeded the configured safety limit")
            output.write(chunk)
    if expected_bytes is not None and total != expected_bytes:
        partial.unlink(missing_ok=True)
        raise ValueError(f"Unexpected download size for {url}: {total} != {expected_bytes}")
    partial.replace(destination)


def selected_matrix_paths(data_dir: Path, raw_dir: Path | None) -> dict[str, Path]:
    """Return selected gzip matrices without unsafe archive extraction."""
    if raw_dir is not None:
        paths = {library.filename: raw_dir / library.filename for library in LIBRARIES}
        missing = [name for name, path in paths.items() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Missing selected matrices in --raw-dir: {missing}")
        return paths

    archive = data_dir / "GSE171524_RAW.tar"
    download_bounded(RAW_ARCHIVE_URL, archive, expected_bytes=EXPECTED_ARCHIVE_BYTES)
    selected_dir = data_dir / "selected_matrices"
    selected_dir.mkdir(parents=True, exist_ok=True)
    allowed = {library.filename for library in LIBRARIES}
    with tarfile.open(archive, mode="r:") as handle:
        members = {member.name: member for member in handle.getmembers() if member.name in allowed}
        missing = sorted(allowed - members.keys())
        if missing:
            raise ValueError(f"NCBI archive is missing expected matrices: {missing}")
        for name, member in members.items():
            target = selected_dir / name
            if target.exists():
                continue
            source = handle.extractfile(member)
            if source is None or not member.isfile():
                raise ValueError(f"Expected regular archive member: {name}")
            with source, target.with_suffix(target.suffix + ".part").open("wb") as output:
                shutil.copyfileobj(source, output)
            target.with_suffix(target.suffix + ".part").replace(target)
    return {name: selected_dir / name for name in allowed}


def canonical_donor(donor: str) -> str:
    return DONOR_ALIASES.get(donor, donor)


def read_public_metadata(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    cells = pd.read_csv(path, sep="\t", skiprows=[1], low_memory=False)
    selected = {canonical_donor(library.donor) for library in LIBRARIES}
    cells["analysis_donor"] = cells["donor_id"].map(canonical_donor)
    cells = cells[cells["analysis_donor"].isin(selected)].copy()

    donors = (
        cells[["analysis_donor", "age", "sex", "group"]]
        .drop_duplicates(subset="analysis_donor")
        .rename(
            columns={
                "analysis_donor": "sample_id",
                "group": "condition",
            }
        )
        .sort_values("sample_id")
        .reset_index(drop=True)
    )
    donors["analysis_partition"] = donors["sample_id"].map(
        lambda donor: "discovery" if donor in DISCOVERY_DONORS else "validation"
    )
    cell_counts = cells.groupby("analysis_donor", observed=True).size()
    donors["annotated_cells"] = donors["sample_id"].map(cell_counts).astype(int)
    return cells, donors


def write_cohortlint_inputs(donors: pd.DataFrame, results_dir: Path) -> Path:
    for partition, frame in donors.groupby("analysis_partition", sort=True):
        frame.drop(columns="analysis_partition").to_csv(
            results_dir / f"{partition}_metadata.csv", index=False
        )
    config = {
        "version": 1,
        "cohorts": [
            {
                "name": "discovery_fold",
                "path": "discovery_metadata.csv",
                "sample_id": "sample_id",
            },
            {
                "name": "validation_fold",
                "path": "validation_metadata.csv",
                "sample_id": "sample_id",
            },
        ],
        "schema": {
            "age": {
                "type": "numeric",
                "unit": "years",
                "range": [0, 120],
                "required": True,
            },
            "sex": {
                "type": "categorical",
                "allowed": ["female", "male"],
                "required": True,
            },
            "condition": {
                "type": "categorical",
                "allowed": ["Control", "COVID-19"],
                "role": "biological",
                "required": True,
            },
            "annotated_cells": {"type": "numeric", "range": [1, 1_000_000], "required": True},
        },
        "privacy": {"k_anonymity_threshold": 3},
        "rules": {"missingness_fraction": 0.1},
        "output": {"lang": "en"},
    }
    config_path = results_dir / "cohortlint.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def run_cohortlint(config_path: Path, report_path: Path) -> None:
    config = load_config(config_path)
    loaded = load_metadata(config)
    context = RuleContext(cohorts=loaded.cohorts, merged=loaded.merged, config=config)
    findings = run_rules(context, set(config.rules.disable))
    overrides = config.rules.severity_overrides
    findings = [
        finding.model_copy(update={"severity": Severity(overrides[finding.rule_id])})
        if finding.rule_id in overrides
        else finding
        for finding in findings
    ]
    score = next(
        (float(finding.evidence["score"]) for finding in findings if finding.rule_id == "D006"),
        100.0,
    )
    report = Report(
        findings=findings,
        cohorts=list(loaded.cohorts),
        n_samples={name: len(frame) for name, frame in loaded.cohorts.items()},
        integrability_score=score,
        generated_at=datetime.now(UTC),
        cohortlint_version=__version__,
    )
    language = resolve_language(config.output.lang)
    report_path.write_text(render_html(report, language) + "\n", encoding="utf-8")
    report_path.with_suffix(".json").write_text(render_json(report) + "\n", encoding="utf-8")


def sum_library_counts(path: Path) -> tuple[pd.Series, int]:
    """Stream a dense gene-by-cell CSV and sum counts without holding it in memory."""
    genes: list[str] = []
    totals: list[int] = []
    with gzip.open(path, mode="rt", encoding="utf-8", newline="") as handle:
        header = handle.readline().rstrip("\r\n").split(",")
        cell_count = len(header) - 1
        if cell_count < 1:
            raise ValueError(f"No cell columns found in {path}")
        for line_number, line in enumerate(handle, start=2):
            separator = line.find(",")
            if separator < 1:
                raise ValueError(f"Malformed row {line_number} in {path}")
            gene = line[:separator].strip('"')
            values = np.fromstring(line[separator + 1 :], sep=",", dtype=np.int64)
            if values.size != cell_count:
                raise ValueError(
                    f"Row {line_number} in {path} has {values.size} counts; expected {cell_count}"
                )
            genes.append(gene)
            totals.append(int(values.sum()))
    series = pd.Series(totals, index=genes, dtype="int64")
    if series.index.has_duplicates:
        series = series.groupby(level=0).sum()
    return series, cell_count


def build_pseudobulk(matrix_paths: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    donor_counts: dict[str, pd.Series] = {}
    qc_rows: list[dict[str, int | str]] = []
    for library in LIBRARIES:
        counts, cells = sum_library_counts(matrix_paths[library.filename])
        donor = canonical_donor(library.donor)
        donor_counts[donor] = donor_counts.get(donor, pd.Series(dtype="int64")).add(
            counts, fill_value=0
        )
        qc_rows.append(
            {
                "library": library.donor,
                "sample_id": donor,
                "matrix_cells": cells,
                "library_counts": int(counts.sum()),
                "detected_genes": int((counts > 0).sum()),
            }
        )
    pseudobulk = pd.DataFrame(donor_counts).fillna(0).astype("int64").sort_index()
    library_qc = pd.DataFrame(qc_rows)
    donor_qc = (
        library_qc.groupby("sample_id", as_index=False)
        .agg(
            matrix_cells=("matrix_cells", "sum"),
            library_counts=("library_counts", "sum"),
            detected_genes=("detected_genes", "max"),
            source_libraries=("library", "count"),
        )
        .sort_values("sample_id")
    )
    return pseudobulk, donor_qc


def benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
    values = np.asarray(p_values, dtype=float)
    result = np.full(values.shape, np.nan)
    finite = np.isfinite(values)
    if not finite.any():
        return result
    subset = values[finite]
    order = np.argsort(subset)
    ranked = subset[order]
    adjusted = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    restored = np.empty_like(adjusted)
    restored[order] = np.clip(adjusted, 0, 1)
    result[finite] = restored
    return result


def analyze_expression(
    counts: pd.DataFrame, donors: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray, list[str]]:
    sample_order = donors["sample_id"].tolist()
    counts = counts.reindex(columns=sample_order)
    library_sizes = counts.sum(axis=0)
    cpm = counts.divide(library_sizes, axis=1) * 1_000_000
    keep = (cpm >= 1).sum(axis=1) >= 3
    log_cpm = np.log2(cpm.loc[keep] + 1)

    conditions = donors.set_index("sample_id").loc[sample_order, "condition"]
    control = conditions[conditions == "Control"].index
    covid = conditions[conditions == "COVID-19"].index
    control_values = log_cpm[control].to_numpy(dtype=float)
    covid_values = log_cpm[covid].to_numpy(dtype=float)
    test = stats.ttest_ind(covid_values, control_values, axis=1, equal_var=False, nan_policy="omit")
    log_fc = covid_values.mean(axis=1) - control_values.mean(axis=1)
    de = pd.DataFrame(
        {
            "gene": log_cpm.index,
            "mean_log2_cpm_control": control_values.mean(axis=1),
            "mean_log2_cpm_covid19": covid_values.mean(axis=1),
            "log2_cpm_difference": log_fc,
            "p_value": test.pvalue,
        }
    )
    de["fdr_bh"] = benjamini_hochberg(de["p_value"].to_numpy())
    de = de.sort_values(["p_value", "gene"], na_position="last").reset_index(drop=True)

    variances = log_cpm.var(axis=1).sort_values(ascending=False)
    pca_genes = variances.head(min(500, len(variances))).index.tolist()
    matrix = log_cpm.loc[pca_genes, sample_order].T.to_numpy(dtype=float, copy=True)
    matrix -= matrix.mean(axis=0, keepdims=True)
    u, singular, _ = np.linalg.svd(matrix, full_matrices=False)
    scores = u[:, :2] * singular[:2]
    explained = singular**2 / np.sum(singular**2) * 100
    return de, log_cpm, scores, explained[:2], pca_genes


def save_plots(
    donors: pd.DataFrame,
    cells: pd.DataFrame,
    qc: pd.DataFrame,
    de: pd.DataFrame,
    log_cpm: pd.DataFrame,
    scores: np.ndarray,
    explained: np.ndarray,
    results_dir: Path,
) -> list[str]:
    colors = {"Control": "#286fb4", "COVID-19": "#c95f45"}
    donor_info = donors.set_index("sample_id")

    merged_qc = qc.merge(donors[["sample_id", "condition"]], on="sample_id")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    plot_qc = merged_qc.sort_values(["condition", "sample_id"])
    bar_colors = plot_qc["condition"].map(colors)
    axes[0].bar(plot_qc["sample_id"], plot_qc["matrix_cells"], color=bar_colors)
    axes[0].set_title("Cells contributing to donor pseudobulk")
    axes[0].set_ylabel("Cell columns in raw matrix")
    axes[1].bar(plot_qc["sample_id"], plot_qc["library_counts"] / 1e6, color=bar_colors)
    axes[1].set_title("Pseudobulk library size")
    axes[1].set_ylabel("Total counts (millions)")
    for axis in axes:
        axis.tick_params(axis="x", rotation=55)
        axis.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(results_dir / "sample_qc.png", dpi=180)
    plt.close(fig)

    composition = (
        cells.groupby(["analysis_donor", "cell_type_main"], observed=True)
        .size()
        .unstack(fill_value=0)
    )
    composition = composition.div(composition.sum(axis=1), axis=0)
    composition.to_csv(results_dir / "cell_type_proportions.csv")
    composition.plot(kind="bar", stacked=True, figsize=(11, 5.5), colormap="tab20")
    plt.title("Annotated cell-type composition by donor")
    plt.xlabel("Donor")
    plt.ylabel("Fraction of annotated cells")
    plt.legend(title="Cell type", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8)
    plt.tight_layout()
    plt.savefig(results_dir / "cell_type_composition.png", dpi=180)
    plt.close()

    fig, axis = plt.subplots(figsize=(7.2, 5.5))
    for index, donor in enumerate(donors["sample_id"]):
        condition = donor_info.loc[donor, "condition"]
        axis.scatter(scores[index, 0], scores[index, 1], color=colors[condition], s=58)
        axis.annotate(
            donor,
            (scores[index, 0], scores[index, 1]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    for condition, color in colors.items():
        axis.scatter([], [], color=color, label=condition)
    axis.set_xlabel(f"PC1 ({explained[0]:.1f}% variance)")
    axis.set_ylabel(f"PC2 ({explained[1]:.1f}% variance)")
    axis.set_title("Donor-level pseudobulk PCA")
    axis.legend(frameon=False)
    axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(results_dir / "pseudobulk_pca.png", dpi=180)
    plt.close(fig)

    plot_de = de[np.isfinite(de["p_value"])].copy()
    plot_de["minus_log10_p"] = -np.log10(plot_de["p_value"].clip(lower=1e-300))
    fig, axis = plt.subplots(figsize=(8, 5.5))
    axis.scatter(
        plot_de["log2_cpm_difference"],
        plot_de["minus_log10_p"],
        color="#91a3af",
        alpha=0.5,
        s=10,
        linewidths=0,
    )
    highlights = plot_de.head(10)
    axis.scatter(
        highlights["log2_cpm_difference"],
        highlights["minus_log10_p"],
        color="#c95f45",
        s=24,
    )
    for row in highlights.itertuples():
        axis.annotate(row.gene, (row.log2_cpm_difference, row.minus_log10_p), fontsize=7)
    axis.axvline(0, color="#263746", linewidth=0.8)
    axis.set_xlabel("Mean log2-CPM difference (COVID-19 - Control)")
    axis.set_ylabel("-log10 exploratory Welch-test p-value")
    axis.set_title("Exploratory donor-level expression comparison")
    axis.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(results_dir / "exploratory_volcano.png", dpi=180)
    plt.close(fig)

    available_markers = [gene for gene in MARKER_GENES if gene in log_cpm.index]
    top_genes = de["gene"].head(20).tolist()
    heatmap_genes = list(dict.fromkeys(available_markers + top_genes))[:24]
    heat = log_cpm.loc[heatmap_genes, donors["sample_id"]]
    row_std = heat.std(axis=1).replace(0, 1)
    heat_z = heat.sub(heat.mean(axis=1), axis=0).div(row_std, axis=0)
    fig, axis = plt.subplots(figsize=(10, max(5, len(heatmap_genes) * 0.27)))
    image = axis.imshow(heat_z, aspect="auto", cmap="RdBu_r", vmin=-2.5, vmax=2.5)
    axis.set_xticks(range(len(heat_z.columns)), heat_z.columns, rotation=55, ha="right")
    axis.set_yticks(range(len(heat_z.index)), heat_z.index)
    axis.set_title("Selected genes: donor-standardized log2-CPM")
    fig.colorbar(image, ax=axis, label="Z-score")
    fig.tight_layout()
    fig.savefig(results_dir / "selected_gene_heatmap.png", dpi=180)
    plt.close(fig)
    return available_markers


def write_summary(
    donors: pd.DataFrame,
    qc: pd.DataFrame,
    de: pd.DataFrame,
    available_markers: list[str],
    results_dir: Path,
) -> None:
    marker_table = de[de["gene"].isin(available_markers)].copy()
    marker_table.to_csv(results_dir / "marker_gene_summary.csv", index=False)
    de.head(250).to_csv(results_dir / "exploratory_de_top250.tsv", sep="\t", index=False)
    qc.merge(donors, on="sample_id").to_csv(results_dir / "sample_qc.csv", index=False)

    missing_age = donors.loc[donors["age"].isna(), "sample_id"].tolist()
    top_rows = de.head(12)[["gene", "log2_cpm_difference", "p_value", "fdr_bh"]].copy()
    top_rows.columns = ["Gene", "log2-CPM difference", "p-value", "BH FDR"]
    summary = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>GSE171524 public transcriptomics case study</title>
<style>
body{{font-family:Arial,sans-serif;color:#263746;max-width:1100px;margin:0 auto;padding:32px;line-height:1.55}}
h1,h2{{color:#16324f}} a{{color:#286fb4}} .hero{{background:#16324f;color:white;padding:28px;border-left:7px solid #168c83}}
.hero h1{{color:white;margin-top:0}} .note{{background:#eaf6f3;border:1px solid #b9ddd6;padding:14px}}
.warn{{background:#fff4df;border-left:5px solid #d99b32;padding:14px}} img{{max-width:100%;height:auto;border:1px solid #d8e2e8}}
table{{border-collapse:collapse;width:100%;font-size:14px}} th,td{{border:1px solid #d8e2e8;padding:7px;text-align:left}} th{{background:#eaf6f3}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}} @media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<div class="hero"><h1>GSE171524: metadata quality gate to real transcriptomics</h1>
<p>A reproducible CohortLint case study using public human-lung single-nucleus RNA-seq data.</p></div>
<p class="note"><b>Data:</b> {len(donors)} donors ({(donors["condition"] == "Control").sum()} control,
{(donors["condition"] == "COVID-19").sum()} COVID-19); {int(qc["matrix_cells"].sum()):,} cell columns summarized;
public source <a href="https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE171524">NCBI GEO GSE171524</a>.</p>
<h2>1. Metadata before expression</h2>
<p>The selected donors were divided into deterministic, condition-balanced discovery and validation folds solely to exercise the multi-table workflow. These are not cohorts claimed by the source study. With the case-study missingness threshold set to 10%, CohortLint flagged the missing age value for {html.escape(", ".join(missing_age) or "none")} and generated a reviewable report.</p>
<p><a href="cohortlint_report.html">Open the standalone CohortLint report</a></p>
<h2>2. Sample-level QC and cell composition</h2><div class="grid">
<img src="sample_qc.png" alt="Sample QC"><img src="cell_type_composition.png" alt="Cell type composition"></div>
<h2>3. Donor-level pseudobulk exploration</h2><div class="grid">
<img src="pseudobulk_pca.png" alt="Pseudobulk PCA"><img src="exploratory_volcano.png" alt="Exploratory volcano plot"></div>
<img src="selected_gene_heatmap.png" alt="Selected gene heatmap">
<h2>Top exploratory gene-level results</h2>{top_rows.to_html(index=False, float_format=lambda value: f"{value:.4g}", border=0)}
<div class="warn"><b>Interpretation boundary.</b> This compact demonstration aggregates all annotated cell types per donor and applies Welch tests to log-CPM values without covariate or cell-composition adjustment. It is not a clinical result, a publication-grade differential-expression model, or a reproduction of the original paper. No FDR threshold is presented as a discovery claim.</div>
<h2>Reproducibility</h2><p>The complete source code, machine-readable outputs, data provenance, and limitations are versioned with CohortLint. Raw public matrices are downloaded from NCBI and are not redistributed.</p>
<p>Source publication: Melms JC et al., <i>A molecular single-cell lung atlas of lethal COVID-19</i>, Nature (2021), <a href="https://doi.org/10.1038/s41586-021-03569-1">doi:10.1038/s41586-021-03569-1</a>.</p>
</body></html>"""
    (results_dir / "analysis_summary.html").write_text(summary, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        help="Use a directory containing the selected .csv.gz matrices instead of downloading.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    results_dir = args.results_dir.resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    metadata_path = data_dir / "GSE171524_lung_metaData.txt.gz"
    download_bounded(METADATA_URL, metadata_path)
    matrix_paths = selected_matrix_paths(data_dir, args.raw_dir.resolve() if args.raw_dir else None)
    cells, donors = read_public_metadata(metadata_path)

    config_path = write_cohortlint_inputs(donors, results_dir)
    run_cohortlint(config_path, results_dir / "cohortlint_report.html")

    pseudobulk, qc = build_pseudobulk(matrix_paths)
    de, log_cpm, scores, explained, _ = analyze_expression(pseudobulk, donors)
    markers = save_plots(donors, cells, qc, de, log_cpm, scores, explained, results_dir)
    write_summary(donors, qc, de, markers, results_dir)
    print(f"Analysis complete: {results_dir / 'analysis_summary.html'}")


if __name__ == "__main__":
    main()
