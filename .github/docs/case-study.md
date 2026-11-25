# Verification and Measurement Protocol

This document records local verification evidence and the live cloud measurement protocol for **Cost-aware GitOps Platform**. See [portfolio notes](portfolio.md) for contribution boundaries, CV wording, and interview talking points. Storefront service code derives from Google Online Boutique (`Apache-2.0`); original engineering work covers the surrounding Terraform infrastructure, GitOps delivery/promotion pipelines, Kyverno/NetworkPolicy security controls, FinOps CLI, and verification/lab readiness suites.

## Run the local checks

Clone the monorepo and run `python scripts/portfolio_demo.py` from the repository root with Python 3.11 or newer. It runs the FinOps and release-digest unit suites plus all three synthetic fixture reports, saving logs and Markdown outputs into a new `.scratch/portfolio-demo-<UTC timestamp>` directory. See the [5-minute demo](demo.md) and [2026-11-16 readiness record](evidence/portfolio-readiness-2026-11-16.md).

To inspect cloud lab prerequisites, regional `Decimal` cost estimates, and dry-run runbook templates without cloud credentials, also run:

```bash
python -m unittest discover -s scripts/tests -v
python scripts/cloud_lab_preflight.py --env nonprod --hours 2
python scripts/cloud_lab_runner.py --dry-run
```

For individual component checks in Bash from the monorepo root (with `kubectl` or `kustomize` installed for overlay rendering):

```bash
for env in dev staging prod preview; do
  kubectl kustomize "gitops-config/apps/boutique/overlays/$env" >/dev/null || exit
done
kubectl kustomize "gitops-config/platform/finops-reporter" >/dev/null || exit

export PYTHONPATH="$PWD/finops-toolkit/src"
python -m unittest discover -s finops-toolkit/tests -v
python -m finops.cli report --fixtures finops-toolkit/tests/fixtures
python -m finops.cli cloud-report --input finops-toolkit/tests/fixtures/focus_sample.csv --as-of 2026-01-19
python -m finops.cli waste --input finops-toolkit/tests/fixtures/custodian --dry-run
```

| Synthetic fixture output | Current window | Baseline / notes |
| --- | ---: | --- |
| OpenCost Kubernetes allocation | `$89.47` | `$104.00` in the prior 7-day window |
| AWS CUR unblended billing | `$140.00` | `$165.00` in the prior 7-day window |
| Multi-cloud FOCUS 1.0/1.1 CSV | `$43.75` | AWS `$8.75`, GCP `$14.00`, Azure `$21.00` per week |
| Cloud Custodian waste candidates | `$27.88 / month` | 4 candidate resources at illustrative default rates |

All numbers above come from committed synthetic fixtures. Because OpenCost workload allocations overlap with underlying AWS EC2/EBS billing in CUR, reports keep the two sources strictly separate. Pre-generated examples can be inspected directly in [weekly-report.md](evidence/weekly-report.md) and [waste-report.md](evidence/waste-report.md).

## Historical Local Verification Record (2026-11-12)

The table below preserves a dated historical verification pass on an earlier pre-remediation revision and is not presented as a fresh hosted CI run. Several compiled test binaries on that Windows sandbox host were constrained by Windows Application Control or loopback socket policies and are noted candidly below.

| Check | Observed historical result |
| --- | --- |
| Terraform | Roots initialized with `-backend=false` and passed `validate`, mocked `terraform test` runs, `fmt`, and Conftest policy checks |
| Infrastructure bootstrap | Bash syntax and mocked command tests passed for `nonprod`, `prod`, and invalid-environment rejection |
| GitOps rendering | All Kustomize paths rendered cleanly, including the scoped `nonprod` downscaler RBAC Application |
| Resource schemas | Standard resources and custom resources validated against Kubernetes 1.35 and pinned CRD schemas |
| Downscaler RBAC scope | Confirmed only `nonprod` grants Namespace `get` on `boutique-dev` and `boutique-staging` |
| Windows host limits | Local Helm/Kyverno/.NET/selected Go test binaries were blocked by Windows Application Control on that host and scheduled for Linux CI runners |
| GitHub workflow syntax | Workflow YAML passed `actionlint` static validation |
| FinOps toolkit | Unit suite and Ruff passed; wheel built and executed fixture reports; 4 Cloud Custodian policies validated |
| Application services | Node (`paymentservice`, `currencyservice`), Python (`emailservice`, `recommendationservice`), Go (`checkoutservice`, `shippingservice`, Linux `CGO_ENABLED=0` cross-builds), Java (`adservice` Gradle assemble), and release/smoke Python tests passed |

## Key Platform Hardening & Remediations Included

- **Offline Terraform plan policy enforcement & governance:** `platform-infra/scripts/offline_plan_check.py` generates offline Terraform JSON plans across `nonprod`, `prod`, `gke`, and `aks` for `conftest test` cost-tag enforcement in `terraform.yml`, paired with `infracost.yml` PR summaries. `envs/prod` requires a non-null monthly AWS Budget (`var.budget`) and documents the 3-NAT (`nat_per_az = true`) vs 1-NAT trade-off.
- **Least-privilege EKS operator access:** `modules/cluster` defaults routine `operator_role_arn` access to `AmazonEKSViewPolicy` while supporting an optional distinct `break_glass_role_arn` (`AmazonEKSClusterAdminPolicy`) for initial Argo CD bootstrap and break-glass recovery. Worker launch templates enforce IMDSv2 (`http_put_response_hop_limit = 1`) and propagate cost tags to EC2 instances and gp3 EBS volumes.
- **Automated digest promotion & expanded Kyverno scope:** `promote-images.yml` and `scanned-images.py --apply-gitops` update `dev`, `staging`, `prod`, and `preview` overlays plus `platform/finops-reporter` with verified GHCR `@sha256` digests (`v0.9` digests are pinned across all overlays). `gitops.yml` SHA-verifies `kubeconform` and `kyverno`, pins `datreeio/CRDs-catalog` by commit SHA, and enforces all four Kyverno policies across both `boutique-*` and `finops` namespaces.
- **Data-safe FinOps & Cloud Lab Readiness Kit:** OpenCost, Athena CUR, and FOCUS CSV readers reject incomplete 14-day windows and nonfinite costs while preserving zero/negative credits. `scripts/cloud_lab_preflight.py` and `scripts/cloud_lab_runner.py` provide `Decimal` session/30-day cost estimates, preflight checks, dry-run evidence generation, and secret/ARN/account-ID log redaction.

## Reproduce Component Checks

Run each command from its component directory after installing documented tools (use Linux or GitHub Actions runners for full Go race, `.NET`, Kyverno CLI, and container Trivy checks):

| Component directory | Verification commands |
| --- | --- |
| `platform-infra` | `make validate`; `make lint`; `make test`; `python3 scripts/offline_plan_check.py --output-dir .scratch/plans`; `conftest verify --policy policies` |
| `gitops-config` | Follow its README local validation loop (`kubectl kustomize` + `kubeconform` + `kyverno test platform/kyverno/tests`) and `.github/workflows/gitops.yml` |
| `finops-toolkit` | `python -m pip install '.[dev,custodian]'`; `make lint test`; `custodian validate custodian/policies/*.yml` |
| `boutique-app` Node | `npm ci --ignore-scripts && npm test` in `src/paymentservice` and `src/currencyservice` |
| `boutique-app` Python | Install `requirements.txt`, then run `python -m unittest discover -v` in `src/emailservice`, `src/recommendationservice`, and `src/loadgenerator` |
| `boutique-app` Go | `go test -race ./...` in `frontend`, `checkoutservice`, `productcatalogservice`, and `shippingservice` |
| `boutique-app` .NET | `dotnet test src/cartservice/tests/cartservice.tests.csproj` |
| `boutique-app` Java | `./gradlew test --no-daemon` in `src/adservice` (`gradlew.bat` on Windows) |
| `boutique-app` & root tooling | `python -m unittest discover -s boutique-app/.github/tests -v` and `python -m unittest discover -s scripts/tests -v` |

Local unit and in-memory gRPC tests do not prove live Kubernetes service discovery, NetworkPolicy, Kyverno admission, Sealed Secrets decryption, and Argo Rollouts progressive delivery working together—that integration boundary is tested by running `smoke-checkout.py` against a deployed cluster.

## Live AWS Lab Measurement Protocol

1. Run `python scripts/cloud_lab_preflight.py --env nonprod --hours 2 --verify-identity --strict` and `python scripts/cloud_lab_runner.py --env nonprod --dry-run`, complete the [AWS lab prerequisites and evidence runbook](runbooks/aws-lab-evidence.md), and provision `nonprod` via the [cluster rebuild runbook](runbooks/khoi-phuc-cluster-tu-git.md).
2. Reconcile the digest-pinned overlays (or promote a new scanned release via `promote-images.yml`), recording merge and healthy Rollout UTC timestamps.
3. In `boutique-dev`, execute the [canary rollback exercise](postmortems/001-canary-tu-rollback.md) so the candidate `/` probe fails, verify `AnalysisRun` abort and continuous stable-pod availability, and restore Git desired state via the [manual rollback runbook](runbooks/rollback-thu-cong.md).
4. For live cost comparisons, collect matched workload windows across 14 complete UTC days and document any node, NAT, Spot-price, or schedule changes affecting spend.

| Metric | Required evidence before claiming a number |
| --- | --- |
| Deployment frequency | Count of healthy production syncs recorded in Argo CD / Git history over a defined window |
| Change lead time | Elapsed UTC time from merged commit to `Healthy` production Rollout |
| Recovery time | Elapsed UTC time from failed candidate detection to passing post-rollback `smoke-checkout.py` (separating stable-pod uptime from Git revert sync) |
| Cluster rebuild time | Elapsed UTC time from `terraform apply` start to first healthy storefront checkout |
| Nonprod cost impact | Matched weekly AWS CUR billing windows explained alongside separate OpenCost namespace allocations |
