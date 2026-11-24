# Portfolio readiness verification — 2026-11-16

## Scope

Executed locally on Windows with Python 3.14.6. This records the current workspace changes; it is not a hosted CI result or a live deployment. The workspace is an export with nested component Git metadata, so a single monorepo commit SHA was not available for this local run. Associate a published commit with a fresh run when sharing it.

Application source originates from Google Online Boutique. The platform, integration checks and FinOps workflow are the project-specific contribution.

## Reproduced offline demo

From the monorepo root:

```text
python scripts/portfolio_demo.py
python -m unittest discover -s scripts/tests -v
```

The final recorded demo started at **2026-11-16T01:15:41.516725+00:00**. Times in this record use UTC. Retained output is in [the run summary](offline-demo-2026-11-16/summary.md).

| Check | Observed result | Evidence |
| --- | --- | --- |
| FinOps unit suite | 42 tests passed | [Full log](offline-demo-2026-11-16/finops-tests.log) |
| Complete scanned-image records | 6 tests passed | [Full log](offline-demo-2026-11-16/digest-tests.log) |
| Weekly synthetic report | OpenCost $89.47 vs $104.00; CUR $140.00 vs $165.00, separate totals | [Report](offline-demo-2026-11-16/weekly-report.md) |
| Multi-cloud synthetic report | AWS/GCP/Azure total 43.75 USD in each comparison week | [Report](offline-demo-2026-11-16/cloud-report.md) |
| Waste fixture | Four candidates, approximately $27.88/month at illustrative default rates | [Report](offline-demo-2026-11-16/waste-report.md) |
| Demo runner integration | 3 tests passed: run from another working directory, retain reports/logs, reject existing output, stop on failure with exit 7, retain partial timeout output | [Full log](offline-demo-2026-11-16/demo-runner-tests.log) |

The demo runner checks were written and observed failing before implementation, then passed after implementation. Independent review identified partial log loss on timeout; a regression test was observed failing, the output handling was corrected and all three runner checks passed. They invoke the real Python commands and verify failure handling; no cloud or socket is required.

## Documentation and automation boundaries

The active workflows live at root `.github/workflows`. Main pushes validate, build and scan with publication disabled. The tag workflow handles only `v0.9` and first checks successful validation of the current main SHA. Deployment promotion is a reviewed manual change in `gitops-config`.

Component apply/drift, automatic promotion/preview and weekly waste workflows remain standalone examples. This change documents their status; it does not activate them. Production Prometheus has a persistent volume; Redis and nonprod Prometheus remain ephemeral. The new demo-runner check is wired into root FinOps CI. Its exact command also passed locally from the `finops-toolkit` working directory; hosted execution has not been verified here. All 73 local file links across the 16 changed/new guides resolved.

## Cloud exercise status

**NOT RUN. No AWS resources created.** The requested limit is zero out-of-pocket cost under Free Tier. No usable local AWS login/profile or kubeconfig is configured, and cloud tools are absent from PATH. EKS, workers, NAT and storage require account-specific eligibility/cost verification; no free deployment is assumed from an account label.

The [AWS evidence checklist](../runbooks/aws-lab-evidence.md) records the prerequisites, checkout/canary/rollback/teardown procedure and unfilled live result table. No deployment, recovery time, production uptime or achieved cost savings are claimed.

## Remaining verification

This pass did not rerun Terraform plans, manifest rendering, Helm/Kyverno, container builds/scans or all application services. Earlier socket-based checks were blocked by Windows/sandbox (`WinError 10013` / independent loopback `EACCES`); Git Bash bootstrap was blocked and Python service dependencies were incomplete. These limits are not reported as passing checks or established application defects. Hosted Actions and AWS Billing remain unverified.
