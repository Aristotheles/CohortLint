# Security policy

## Supported versions

Security fixes are provided for the latest published CohortLint release.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting for the repository. Do not include real
patient metadata, direct identifiers, credentials, or API tokens in a report.

## Threat model and OWASP review

CohortLint is a local CLI rather than a web service, so authorization and session-management
categories are not directly exposed. The relevant OWASP Top 10 and high-risk controls are:

- **Injection:** YAML uses `safe_load`; no shell command is built from metadata; HTML uses
  Jinja autoescaping and a restrictive Content Security Policy.
- **Cryptographic failures / sensitive-data exposure:** P001 evidence contains pattern counts
  only. Reports never include matched direct-identifier values.
- **Security misconfiguration:** GitHub Actions have least-privilege permissions and release
  jobs use OIDC Trusted Publishing instead of stored PyPI credentials.
- **Vulnerable components:** runtime dependencies are permissively licensed and CI runs
  `pip-audit`. Actions are pinned to immutable commit SHAs.
- **Integrity failures:** releases are built in CI from tagged GitHub releases; PyPI upload is
  restricted to the `pypi` environment and OIDC identity.
- **SSRF / unsafe network use:** core checks perform no network requests. Ontology access is an
  explicit optional extra and prefers a bounded local cache.
- **Path and overwrite risks:** report and harmonization outputs cannot overwrite config or
  cohort inputs; ontology cache filenames are sanitized and symlink overwrites are refused.

CSV files preserve scientific values exactly. Treat spreadsheet opening as a separate trust
boundary because untrusted source values beginning with formula characters may be interpreted
by spreadsheet software. Prefer the JSON or HTML report for untrusted metadata review.
