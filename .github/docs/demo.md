# 5-Minute Portfolio Demo

This walkthrough demonstrates platform boundaries, automated verification, and cost-reporting safeguards for engineering reviewers. It requires only Python 3.11 or newer—no third-party package installation, cloud login, or open network sockets. All figures come from committed synthetic fixtures and do not claim a live cloud deployment or measured cloud savings.

## Setup and Execution

Clone the monorepo following the [quick-start guide](quick-start.md), then run from the repository root in PowerShell or Bash:

```bash
python scripts/portfolio_demo.py
```

The runner prints a new evidence directory path under `.scratch/portfolio-demo-<UTC timestamp>`. Every run writes to a fresh directory; you can pass `--output-dir <path>`, and existing directories are rejected so prior evidence is never overwritten.

| Output file | What to highlight |
| --- | --- |
| `summary.md` | UTC start timestamp, Python version, each executed command, and nonzero exit code on failure |
| `finops-tests.log` | Unit tests covering missing billing days, negative credits, multi-currency totals, notifications, and report formatting |
| `digest-tests.log` | Release-record checks enforcing complete service digest sets, source revision matching, and overlay promotion updates |
| `weekly-report.md` | OpenCost (`$89.47` vs `$104.00`) and AWS CUR (`$140.00` vs `$165.00`) shown separately rather than summed |
| `cloud-report.md` | Normalized AWS/GCP/Azure FOCUS CSV comparison totaling `43.75 USD` in each 7-day window |
| `waste-report.md` | Four Cloud Custodian candidates (`~$27.88/month` at illustrative default rates) |

If waste-pricing environment variables (`EBS_GB_MONTH_RATE`, `EIP_HOURLY_RATE`, `SNAPSHOT_GB_MONTH_RATE`, `ALB_HOURLY_RATE`) are set in your shell, the CLI honors them; clear overrides before comparing against default fixture numbers. The runner halts immediately if any command exits nonzero and preserves partial logs. Verify `summary.md` before presenting results.

To preview cloud lab readiness, itemized `ap-southeast-1` hourly/session/30-day `Decimal` cost estimates, and a dry-run evidence template without touching cloud credentials, run:

```bash
python scripts/cloud_lab_preflight.py --env nonprod --hours 2
python scripts/cloud_lab_runner.py --dry-run
```

## 5-Minute Walkthrough Script

| Time | What to open | Talking points |
| --- | --- | --- |
| 0:00–0:45 | [Architecture overview](architecture/overview.md) | Online Boutique is Google's sample microservice storefront; original project work covers Terraform infrastructure, CI/GitOps delivery, Kyverno/NetworkPolicy guardrails, FinOps reporting, and test harnesses. Separate source code, immutable container digests, and Git desired state. |
| 0:45–1:30 | Terminal output and `summary.md` | Show real offline commands executing locally (FinOps unit suite and release-digest promotion tests). State clearly that these run against local fixtures without cloud credentials. |
| 1:30–2:30 | `weekly-report.md` and `cloud-report.md` | Explain why OpenCost Kubernetes workload allocations and AWS CUR billing overlap and must never be added together. Open `finops-toolkit/tests/test_athena.py` to show how incomplete 14-day windows fail fast instead of treating missing days as `$0`. |
| 2:30–3:30 | Root `.github/workflows/ci.yml`, `release.yml`, `promote-images.yml`, and `digest-tests.log` | `main` pushes validate, build, and Trivy-scan without pushing images. Tag `v0.9` verifies a green `Release validation` run on `main`, publishes signed/scanned GHCR digests, and invokes `promote-images.yml` to open a reviewed GitOps PR updating Kustomize overlays (`dev`, `staging`, `prod`, `preview`) and `finops-reporter`. |
| 3:30–4:30 | `frontend-rollout.yaml`, `analysis-template.yaml`, and [manual rollback runbook](runbooks/rollback-thu-cong.md) | Explain the `/` blackbox probe and replica-based canary weights. Note that an automatic Rollout abort keeps stable pods serving while Git still references the failed candidate until a revert PR restores desired state. |
| 4:30–5:00 | [Readiness record](evidence/portfolio-readiness-2026-11-16.md) and `cloud_lab_preflight.py` | Summarize verified offline checks versus live cloud prerequisites: private EKS API routing, `TF_VAR_break_glass_role_arn` for initial Argo CD bootstrap, ephemeral Redis/nonprod Prometheus tradeoffs, and explicit hourly lab costs. |

## Questions You Should Be Ready to Answer

- Why deploy immutable `@sha256` digests in Kustomize overlays instead of mutable tags, and how does `scanned-images.py` handle an incomplete service artifact set?
- Why must OpenCost allocations and AWS CUR unblended totals remain separate, and how do negative credits or missing daily partitions affect weekly comparisons?
- Why does `prod` require manual Argo CD sync and a mandatory monthly `TF_VAR_budget`, and how does a canary abort differ from a Git revert?
- Does scaling replicas to zero after hours (`GoKubeDownscaler`) automatically reduce EC2 spend on fixed-size managed node groups?
- What state is lost when an ephemeral Redis or nonprod Prometheus pod restarts, and why does production Prometheus use a `Retain` `gp3` volume?

To demonstrate a live storefront checkout, provision a cluster with [cluster rebuild from Git](runbooks/khoi-phuc-cluster-tu-git.md) and run `smoke-checkout.py` against the port-forwarded frontend. The offline demo does not bind network sockets, provision cloud infrastructure, or send external alert notifications.
