# CI Triage — References

## Retina artifact layout

`https://gitlab.com/ocudu/ocudu_infra_srs/-/raw/main/retina/launcher/artifacts.md`

Describes the directory structure under `e2e/log/tests/` for E2E jobs: element names, timestamp directories, and which files to read for each failure type. Fetch once on the first E2E job and reuse for subsequent ones.

## E2E test suite structure

`https://gitlab.com/ocudu/ocudu_infra_srs/-/raw/main/e2e/tests/README.md`

Describes how test suites, configs, criteria, and suite params are organised. Useful for interpreting test IDs (e.g. `mobility.inter_du_ho.fr1_fr2`) and deriving accurate search keywords.
