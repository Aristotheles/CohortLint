# GSE171524 public single-nucleus RNA-seq case study

This reproducible case study connects CohortLint's metadata quality gate to a small,
real downstream transcriptomics analysis. It uses public data from NCBI GEO accession
[GSE171524](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE171524), a human lung
single-nucleus RNA-seq study containing COVID-19 and control donors.

## What the workflow does

1. Downloads the public cell metadata and raw count archive from NCBI GEO.
2. Selects 13 donors (7 control and 6 COVID-19) to keep the demonstration practical.
3. Creates two deterministic, condition-balanced analysis partitions. These partitions are
   **demonstration folds, not cohorts reported by the original study**.
4. Runs CohortLint before expression analysis and writes a standalone HTML report.
5. Aggregates cell-level counts to donor-level pseudobulk profiles.
6. Produces sample QC, cell-composition, PCA, exploratory differential-expression, and
   marker-gene summaries.
7. Writes a self-contained HTML overview and machine-readable CSV/TSV results.

## Versioned results

- [Analysis overview](results/analysis_summary.html)
- [CohortLint HTML report](results/cohortlint_report.html) and
  [machine-readable JSON](results/cohortlint_report.json)
- [Sample QC](results/sample_qc.csv), [cell-type proportions](results/cell_type_proportions.csv),
  and [top exploratory expression results](results/exploratory_de_top250.tsv)

In the selected subset, CohortLint flags one missing age value in the six-donor validation
fold (16.7% at the case-study's 10% missingness threshold) and small quasi-identifier groups
in both demonstration folds. PCA shows that the first two components explain 50.7% and 17.1%
of variance. Interferon-response markers including IFITM3, ISG15, and IFIT3 are higher on
average in the COVID-19 donor pseudobulks, but the aggregate comparison is strongly exposed
to cell-composition and other confounding and must remain exploratory.

## Reproduce the analysis

From the repository root:

```bash
python -m pip install -e ".[case-study]"
python case_studies/gse171524/analyze.py
```

The NCBI archive is approximately 170 MB. Downloaded source files are stored under
`case_studies/gse171524/data/` and are excluded from Git. Versioned outputs are written to
`case_studies/gse171524/results/`.

For an already extracted set of the selected `*.csv.gz` matrices:

```bash
python case_studies/gse171524/analyze.py --raw-dir PATH_TO_MATRICES
```

## Interpretation boundary

This is an educational, exploratory reanalysis and not a clinical result or a reproduction
of the original paper. The donor-level Welch tests use log-CPM values and do not model
covariates, cell-type composition, or the negative-binomial mean-variance relationship.
They are included to demonstrate a transparent end-to-end workflow; publication-grade
differential expression would require a prespecified model and a tool such as edgeR or
DESeq2. The source study and its publication remain the authoritative references.

## Public-data citation

- GEO: GSE171524, *Columbia University/NYP COVID-19 Lung Atlas*.
- Melms JC et al. *A molecular single-cell lung atlas of lethal COVID-19.* Nature (2021).
  DOI: [10.1038/s41586-021-03569-1](https://doi.org/10.1038/s41586-021-03569-1).
