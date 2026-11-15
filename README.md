# Cost-aware GitOps Platform

A portfolio lab for delivering Google Online Boutique with Terraform, Argo CD, automated image promotion and cost reporting. The primary path uses AWS EKS; optional nonprod Terraform roots support GKE and AKS.

**v0.9 preparation:** [Changes, review reconciliation and release gates](.github/docs/releases/v0.9.md). Release validation and GitHub publication are still pending.

The engineering work in this project is the platform, delivery automation, FinOps tooling and integration tests. The storefront and its microservices originate from Google's Apache-2.0-licensed [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo).

**Start here:** [Portfolio and CV notes](.github/docs/portfolio.md) · [Architecture](.github/docs/architecture/overview.md) · [Verification and demo](.github/docs/case-study.md)

**Hướng dẫn tiếng Việt:** [Quick-start từ offline đến cloud](.github/docs/quick-start.md) · [Đối chiếu sáu điểm yếu và cách khắc phục](.github/docs/comparison-remediation.md)

## Workspace

This release is a monorepo published at [workwithcrow12-art/cost-aware-gitops-platform](https://github.com/workwithcrow12-art/cost-aware-gitops-platform). Active workflows live in `.github/workflows`. Nested component workflows are retained as standalone examples and do not run here. Run component commands from their named directory.

| Component | Contribution |
|---|---|
| [platform-infra](platform-infra/README.md) | Private EKS clusters, optional GKE/AKS labs, remote state, budget alerts, Athena catalog/IAM, cost tags and Terraform policy checks |
| [gitops-config](gitops-config/README.md) | Environment separation, digest-pinned releases, frontend canaries, admission and network policies, scheduled nonprod scaling and observability |
| [boutique-app](boutique-app/README.md) | Service tests, image build/scan/publish workflow, reviewed preview releases and checkout smoke test |
| [finops-toolkit](finops-toolkit/README.md) | Weekly OpenCost/Athena reports, multi-cloud FOCUS billing comparisons, missing-data checks and read-only waste estimates |
| [.github](.github/README.md) | Organization profile, architecture decisions, runbooks and portfolio evidence |

## Try it without AWS

With Python 3.11 or newer, run from this directory. The commands use committed synthetic data and do not contact cloud services or send notifications.

```powershell
$env:PYTHONPATH = (Resolve-Path finops-toolkit/src).Path
python -m unittest discover -s finops-toolkit/tests -v
python -m finops.cli report --fixtures finops-toolkit/tests/fixtures
python -m finops.cli cloud-report --input finops-toolkit/tests/fixtures/focus_sample.csv --as-of 2026-01-19
python -m finops.cli waste --input finops-toolkit/tests/fixtures/custodian --dry-run
```

In Bash, replace the first line with `export PYTHONPATH="$PWD/finops-toolkit/src"`.

Read the generated [weekly report](.github/docs/evidence/weekly-report.md) and [waste summary](.github/docs/evidence/waste-report.md). Both use synthetic fixtures; their numbers are not measured savings.

## Scope of the portfolio version

Local tests, infrastructure mock plans and manifest rendering establish the evidence recorded in the [case study](.github/docs/case-study.md). They do not establish a successful AWS deployment. The AWS rebuild, actual canary/rollback exercise and deployed checkout smoke remain separately documented lab procedures.

The design deliberately uses fixed node groups, ephemeral Redis and nonprod Prometheus storage, mock payment/email services and an optional reporting CronJob. The production profile includes persistent Prometheus storage. Production operation still requires availability, notification destinations, backups and recovery verification.

To run the AWS lab, follow the [rebuild runbook](.github/docs/runbooks/khoi-phuc-cluster-tu-git.md). Publishing these repositories, configuring GitHub credentials and provisioning AWS are separate operator steps.
