# Review Comparison and Remediation Record

## Initial Comparison — 2026-11-14

Reconciled against an external architecture critique (`cost-aware-comparison.md`) supplied on 2026-11-14. Proposed tools in that critique were evaluated against existing repository capabilities to avoid redundant stacks.

| Reported gap | Actual baseline and remediation | Verification evidence |
| --- | --- | --- |
| AWS EKS only | Added optional private Terraform roots `envs/gke` and `envs/aks` with network isolation, node identities, operator access controls, NetworkPolicy enforcement, and cost labels/tags. Updated `bootstrap-argocd.sh` to accept explicit kubeconfig contexts and a `managed` profile (`bootstrap/nonprod-managed`) omitting duplicate `metrics-server` while preserving EKS auto-discovery. | `terraform validate` + mocked `terraform test` suites + bootstrap script unit tests. Live GKE/AKS clusters not yet provisioned. |
| Manual Athena DB/table/IAM setup | Extended `modules/cost-reporting` beyond workgroup-only setup to provision a private encrypted/TLS S3 results bucket, Glue database/table for legacy Parquet CUR, prefix-scoped IRSA role for `finops-reporter`, and configuration outputs wired into shared bootstrap and environment roots. | Mocked Terraform tests covering full catalog + IRSA mode, legacy workgroup-only mode, and invalid input rejection. Billing export activation in AWS Billing remains an account step. |
| No multi-cloud cost aggregation | Added `finops cloud-report` normalizing FOCUS 1.0/1.1 CSV exports grouped by provider, environment, and team with per-currency separation and strict 14-day completeness validation—without requiring a commercial Kubecost license. | Multi-cloud AWS/GCP/Azure fixtures, unit tests, CLI checks, and container smoke runs in CI. Does not pull billing APIs directly. |
| Reliance on an OpenCost sandbox install | Repository already managed a version-pinned OpenCost Helm release (`2.5.20`) via the `platform-addons` Argo CD `ApplicationSet`. Kept a single GitOps-managed Helm release and documented deployment/API verification and missing-metric troubleshooting. | Verified pinned chart configuration, rendered `ApplicationSet`, and Prometheus `ServiceMonitor` wiring. Live cluster sync still requires an operator lab run. |
| Missing CI policy tests | Repository already executed `kyverno test` in GitHub Actions; expanded test coverage across partial resource limits, `initContainers`, `ephemeralContainers`, Deployment pod-template autogen, and namespace exclusions. | Kyverno CLI `1.18.1` offline policy test suite passing in CI without adding a duplicate `kuttl` cluster harness. |
| Unclear cross-component workflow | Added an end-to-end [quick-start guide](quick-start.md) walking from zero-credential offline checks -> cloud root selection -> GitOps bootstrap -> Athena/FOCUS billing -> pre-PR validation, with explicit directory boundaries and operational caveats. | Offline demo runner, mocked Terraform plans, bootstrap tests, and Kustomize/Kubeconform manifest rendering. |

## Follow-Up Hardening & Monorepo Remediation — 2026-11

Subsequent engineering review closed remaining automation, supply-chain, governance, and usability gaps across the monorepo:

| Remediation area | Implemented changes | Verification |
| --- | --- | --- |
| Offline Terraform plan policy gate & Infracost CI | Added `platform-infra/scripts/offline_plan_check.py` (stdlib local AWS/Azure/GCP provider stubs) generating real `terraform show -json` plans for `nonprod`, `prod`, `gke`, and `aks` in `.github/workflows/terraform.yml`, checked by `conftest test` (`policies/tagging.rego`) alongside `infracost.yml` PR cost breakdowns. | Unit tests (`platform-infra/tests`) + Conftest policy verification + CI workflow gate. |
| Release gating & automated GitOps digest promotion | Removed `paths-ignore` on `main` pushes in `ci.yml` so every `main` commit records a `Release validation` run; `release.yml` accepts `push` or `workflow_dispatch` validation runs and triggers `.github/workflows/promote-images.yml` (`scanned-images.py --apply-gitops`) to open reviewed digest-promotion PRs across `dev`, `staging`, `prod`, `preview`, and `finops-reporter`. Pinned live `v0.9` GHCR `@sha256` digests across all overlays. | `test_scanned_images.py` + Kustomize/Kubeconform overlay rendering. |
| Supply-chain & Kyverno `finops` coverage | Verified SHA-256 checksums for `kubeconform` (`v0.7.0`) and `kyverno` (`v1.18.1`) before extraction and pinned `datreeio/CRDs-catalog` by commit SHA in `gitops.yml`. Extended all four Kyverno policies (`require-image-digest`, `require-cost-labels`, `require-resource-limits`, `require-restricted-pods`) and CI pod checks to the `finops` namespace (`finops-reporter`). | Kyverno test suite + rendered `finops-reporter` CronJob pod policy check. |
| Least-privilege EKS access, mandatory `prod` budget, & root OIDC workflows | Defaulted `operator_access_policy` to `AmazonEKSViewPolicy` with optional distinct `break_glass_role_arn` (`AmazonEKSClusterAdminPolicy`) for initial bootstrap/recovery; made `var.budget` mandatory in `envs/prod` and parameterized `nat_per_az` with `ap-southeast-1` cost documentation; promoted SHA-pinned `terraform-apply.yml`, `terraform-drift.yml`, and `custodian-weekly.yml` to root `.github/workflows/` and retired dormant nested workflows; added Dependabot coverage for all Terraform modules. | Mocked `.tftest.hcl` positive/negative assertions + root workflow validation. |
| Turnkey Cloud Lab Readiness Kit & English documentation | Added `scripts/cloud_lab_preflight.py` (`Decimal` cost estimator + tool/env/private-API checks) and `scripts/cloud_lab_runner.py` (`--dry-run` plan/evidence generator + redacted live stage logging), standardized all operational documentation in English in-place, and documented solo-maintainer GitHub Ruleset guidance. | `scripts/tests/test_cloud_lab.py` + `test_portfolio_demo.py` + link and language checks. |

## Historical Local Verification Snapshot (2026-11-14)

- **Python:** FinOps unit test suite and bootstrap script checks (EKS default, explicit kubeconfig context, and `managed` profile).
- **Terraform 1.11.4:** `fmt`, `validate`, and mocked `terraform test` runs across roots and modules, including legacy Athena workgroup compatibility.
- **Kyverno 1.18.1:** Policy test suite passing across Pod, initContainer, Deployment, and namespace-scope cases.
- **Kustomize (`kubectl` 1.35) & Kubeconform:** All Kustomize roots rendered cleanly with zero invalid standard or CRD schemas.
- **OpenCost:** Confirmed pinned Helm chart `2.5.20`, `ApplicationSet` wiring, and Prometheus `ServiceMonitor` configuration.

Local verification does not create cloud resources, publish container images, or emit external notifications, and does not substitute for end-to-end integration testing on live EKS/GKE/AKS infrastructure or reconciliation against finalized cloud invoices.
