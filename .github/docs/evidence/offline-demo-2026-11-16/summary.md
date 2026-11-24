# Offline portfolio demo

Started (UTC): 2026-11-16T01:15:41.516725+00:00
Python: 3.14.6
Working directory: monorepo root

Synthetic fixtures only. No cloud deployment or measured savings are established.
Commands below use shell notation; Python uses the current interpreter.

- finops-tests.log: **PASS**
  - Command: `python -m unittest discover -s finops-toolkit/tests -v`
- digest-tests.log: **PASS**
  - Command: `python -m unittest discover -s boutique-app/.github/tests -p test_scanned_images.py -v`
- weekly-report.md: **PASS**
  - Command: `python -m finops.cli report --fixtures finops-toolkit/tests/fixtures`
- cloud-report.md: **PASS**
  - Command: `python -m finops.cli cloud-report --input finops-toolkit/tests/fixtures/focus_sample.csv --as-of 2026-01-19`
- waste-report.md: **PASS**
  - Command: `python -m finops.cli waste --input finops-toolkit/tests/fixtures/custodian --dry-run`
