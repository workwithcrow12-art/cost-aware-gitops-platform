# Portfolio and CV Notes

## Project Summary

**Cost-aware GitOps Platform — AWS EKS, Terraform, Argo CD, Kyverno, GitHub Actions, Python**

Designed and implemented a reference DevOps and FinOps platform connecting private Kubernetes infrastructure, supply-chain-verified GitOps image promotion, progressive delivery policies, and multi-source cloud cost reporting around Google's Online Boutique microservices workload. Root monorepo CI validates source, offline Terraform plans, Kyverno policies, and container scans on every `main` push; tagged releases publish digest-pinned GHCR images and open reviewed GitOps promotion PRs automatically via `promote-images.yml`.

This repository is structured for engineering code review, zero-credential local verification, turnkey cloud lab preflight planning, and technical interviews. See the [verification and measurement protocol](case-study.md) for exact local evidence boundaries. Live cloud operation and measured production cost savings are never claimed without timestamped lab logs.

## CV Bullet Wording

- Built a private AWS EKS (plus optional GKE/AKS lab) platform with Terraform and Argo CD featuring least-privilege `AmazonEKSViewPolicy` operator access with distinct break-glass admin roles, offline plan OPA/Conftest cost-tag gates, mandatory production AWS Budgets, digest-pinned image promotion PRs, Prometheus-probed Argo Rollouts frontend canaries, and Kyverno `restricted` pod/supply-chain enforcement across application and FinOps namespaces.
- Implemented a zero-float (`Decimal`) Python FinOps CLI comparing OpenCost Kubernetes workload allocations separately from AWS CUR/Athena billing, normalizing multi-cloud FOCUS 1.0/1.1 CSV spend while rejecting incomplete 14-day windows, and estimating monthly waste from read-only Cloud Custodian findings.
- Created a credential-free verification and Cloud Lab Readiness suite (`portfolio_demo.py`, `cloud_lab_preflight.py`, `cloud_lab_runner.py`) covering multi-language service/checkout tests, mocked and offline-planned Terraform checks, regional `ap-southeast-1` hourly/30-day cost modeling, and secret-redacted runbook evidence capture.

Attribute the sample storefront services to Google Online Boutique (`Apache-2.0`), framing your original work around platform infrastructure, CI/CD & GitOps automation, security/admission policies, FinOps engineering, and verification tooling. Never present synthetic fixture percentages as achieved cloud savings or claim live cluster uptime without corresponding lab evidence.

## Five-Minute Interview Walkthrough

Follow the runnable commands and timing table in the [5-minute demo script](demo.md):

1. Walk through the [platform architecture](architecture/overview.md): application source, GHCR immutable digests, `promote-images.yml` GitOps PRs, Argo CD environment isolation, private EKS access model, and separate billing pipelines.
2. Run the [local offline checks](case-study.md#run-the-local-checks) and inspect the [synthetic weekly cost report](evidence/weekly-report.md), explaining why OpenCost allocations and AWS CUR billing overlap and why missing daily partitions fail fast rather than defaulting to `$0`.
3. Show service unit tests, `smoke-checkout.py`, and `cloud_lab_preflight.py --env nonprod --hours 2`, distinguishing local test harnesses and offline cost/readiness checks from an authenticated end-to-end storefront smoke run.
4. Trace the release and rollback lifecycle: Trivy-gated image publication, `scanned-images.py --apply-gitops` overlay promotion PRs, frontend `/` canary probing, automatic Rollout abort, and explicit `git revert` desired-state restoration.
5. Discuss explicit operational tradeoffs (fixed node counts vs pod downscaling, 1 vs 3 NAT Gateways, ephemeral Redis/nonprod Prometheus vs `Retain` gp3 production Prometheus) and the measurement protocol required before claiming cloud savings.

## Key Engineering Tradeoffs to Discuss

| Decision | Rationale and tradeoff |
| --- | --- |
| Unified monorepo with reviewed GitOps overlay PRs | Keeps infrastructure, apps, policies, and FinOps atomic while `promote-images.yml` records exact `@sha256` digest transitions in reviewable Git history before Argo CD syncs. Dormant nested workflows were retired in favor of root `.github/workflows/`. |
| Least-privilege `AmazonEKSViewPolicy` + optional `break_glass_role_arn` | Routine operator access defaults to read-only cluster visibility, while initial `bootstrap-argocd.sh` and emergency recovery explicitly assume a separate `AmazonEKSClusterAdminPolicy` role. |
| Helm for platform add-ons, Kustomize for app overlays | Consumes version-pinned upstream Helm charts (`argo-cd`, `opencost`, `kyverno`, `kube-prometheus-stack`) while keeping environment-specific Boutique patches and digest replacements concise. |
| Canary progressive delivery scoped to `frontend` | Demonstrates Prometheus-gated Rollout analysis and automatic abort without requiring a full service mesh across 10 internal gRPC backends; replica weights approximate traffic ratios. |
| Immutable GHCR `@sha256` digests + Kyverno in `boutique-*` and `finops` | Prevents mutable tag drift across both storefront services (`v0.9` GHCR digests in overlays) and the `finops-reporter` CronJob while keeping `base/` cleanly keyed to upstream image names. |
| Fixed Spot (`nonprod`) and On-Demand (`prod`) node groups + `nat_per_az` | Makes baseline hourly costs transparent (`$0.2403/hr` nonprod Spot with 1 NAT vs `$0.6477/hr` prod On-Demand with 3 NATs in `ap-southeast-1`); `GoKubeDownscaler` lowers off-hours pod counts without removing fixed EC2 nodes unless opt-in Karpenter is enabled. |
| Separate OpenCost and AWS CUR/FOCUS totals | Workload resource allocation and cloud invoices overlap and arrive on different schedules; strict 14-day completeness checks prevent incomplete data from masquerading as cost reductions. |
| Ephemeral Redis/nonprod Prometheus vs `Retain` prod Prometheus PVC | Simplifies disposable lab runs while documenting data-loss boundaries on pod restart and explicit EBS cleanup requirements for `Retain` volumes. |

See the [Architecture Decision Records](adr/) for historical context on each design boundary.

## Pre-Publication Checklist

The canonical repository is [workwithcrow12-art/cost-aware-gitops-platform](https://github.com/workwithcrow12-art/cost-aware-gitops-platform). When adapting a fork, update repository URLs in `gitops-config/`, workflow owner references, and `.github/CODEOWNERS`. Root `README.md` serves as the portfolio landing page (`.github/profile/README.md` is a retained org-profile template).

Configure GitHub Rulesets on `main` following [CONTRIBUTING.md](../CONTRIBUTING.md) (require `Release validation` status checks; keep Code Owner review non-deadlocking while solo-maintained). Opt-in root operational workflows (`terraform-apply.yml`, `terraform-drift.yml`, `custodian-weekly.yml`) remain gated behind explicit OIDC roles, repository variables (`TF_DRIFT_ENABLED`, `CUSTODIAN_LIVE_ENABLED`, `TF_PROD_BUDGET_JSON`), and GitHub Environment approvals. Neither publishing images nor running local checks requires cloud credentials to reproduce the offline demo.
