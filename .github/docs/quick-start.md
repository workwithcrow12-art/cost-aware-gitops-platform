# Getting Started with Cost-aware GitOps Platform

## 1. Component Boundaries and Data Flow

| Directory | Primary workflow | Handoff to downstream components |
| --- | --- | --- |
| `platform-infra` | Terraform provisions VPCs, private Kubernetes clusters, access policies, S3 state, AWS Budgets, OIDC, and optional Athena/Karpenter; bootstraps Argo CD | Supplies kubeconfig context for `gitops-config` and Athena/IRSA outputs for `finops-reporter` |
| `gitops-config` | Argo CD reconciles platform add-ons, Kyverno policies, and digest-pinned Online Boutique overlays from Git | Exposes OpenCost allocation API and Prometheus metrics to `finops-toolkit` |
| `boutique-app` | Runs multi-language service tests, container builds, Trivy scans, and digest promotion tooling (`scanned-images.py`) | Feeds verified GHCR `@sha256` digests into `gitops-config` overlays via `promote-images.yml` PRs |
| `finops-toolkit` | Generates OpenCost + AWS CUR weekly comparisons, multi-cloud FOCUS CSV reports, and Cloud Custodian waste summaries | Emits Markdown reports to stdout/logs with optional Slack or Telegram failure alerts |
| `.github` & `scripts` | Root monorepo CI/CD workflows, architecture docs, runbooks, offline demo runner, and Cloud Lab Readiness Kit | Entry point for local verification, release automation, and cloud lab execution |

Clone the monorepo once and run component-specific commands from the directory noted in each step. All active GitHub Actions workflows live at root `.github/workflows/` (dormant nested `.github/workflows` directories were retired into unified root workflows).

```bash
git clone https://github.com/workwithcrow12-art/cost-aware-gitops-platform.git
cd cost-aware-gitops-platform
```

## 2. Run the Offline Demo First (Zero Cloud Credentials)

Install Python 3.11 or newer. From the monorepo root, run `python scripts/portfolio_demo.py` to execute the offline test suites and save logs plus all three synthetic FinOps reports in a fresh `.scratch/portfolio-demo-<UTC timestamp>` directory (see the [5-minute walkthrough](demo.md)). Equivalent individual commands in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path finops-toolkit/src).Path
python -m unittest discover -s finops-toolkit/tests -v
python -m finops.cli report --fixtures finops-toolkit/tests/fixtures
python -m finops.cli cloud-report --input finops-toolkit/tests/fixtures/focus_sample.csv --as-of 2026-01-19
python -m finops.cli waste --input finops-toolkit/tests/fixtures/custodian --dry-run
```

In Bash, replace the first line with `export PYTHONPATH="$PWD/finops-toolkit/src"`. All figures come from synthetic fixtures: `cloud-report` outputs `43.75 USD` per week (`AWS 8.75`, `Google Cloud 14.00`, and `Microsoft Azure 21.00 USD`). These numbers verify parser and comparison behavior rather than measured cloud spend, and `cloud-report` never sends external notifications.

Before provisioning any live infrastructure, run the offline Cloud Lab Readiness Kit to inspect local CLI binaries, required environment variables, private Kubernetes API caveats, and itemized regional `Decimal` cost estimates:

```bash
python scripts/cloud_lab_preflight.py --env nonprod --hours 2
python scripts/cloud_lab_runner.py --env nonprod --dry-run
```

## 3. Select a Cloud Cluster Root for a Live Lab

| Cloud | Terraform root in `platform-infra` | Authentication and access prerequisites |
| --- | --- | --- |
| AWS (primary) | `envs/nonprod`, `envs/prod` | Follow the [EKS rebuild runbook](runbooks/khoi-phuc-cluster-tu-git.md) for S3 state backend, routine `TF_VAR_operator_role_arn` (`AmazonEKSViewPolicy`), bootstrap `TF_VAR_break_glass_role_arn` (`AmazonEKSClusterAdminPolicy`), and mandatory `prod` `TF_VAR_budget` |
| GCP (optional lab) | `envs/gke` | Billing-enabled project; `gcloud auth application-default login`; install `gke-gcloud-auth-plugin` |
| Azure (optional lab) | `envs/aks` | Active Azure subscription and Microsoft Entra admin group; `az login`; install `kubelogin` |

Running `terraform apply` against any cloud root creates billable infrastructure. `envs/gke` and `envs/aks` are fixed two-node nonproduction lab configurations that have been validated with Terraform tests and offline plans rather than live cloud deployments: `envs/gke` uses a single zone (`asia-southeast1-a`) to avoid multiplying node charges across zones, and `envs/aks` uses Azure lab defaults rather than a multi-zone production SLA architecture.

For **GKE**, run from `platform-infra`:

```bash
cp envs/gke/terraform.tfvars.example envs/gke/lab.secret.tfvars
# Populate project_id, operator_member, and routed VPN/bastion CIDRs in lab.secret.tfvars.
terraform -chdir=envs/gke init
terraform -chdir=envs/gke plan -var-file=lab.secret.tfvars -out=lab.tfplan
terraform -chdir=envs/gke apply lab.tfplan
terraform -chdir=envs/gke output -raw get_credentials_command
# Execute the printed gcloud command from a host with private control-plane routing.
```

For **AKS**, run from `platform-infra`:

```bash
cp envs/aks/terraform.tfvars.example envs/aks/lab.secret.tfvars
# Populate subscription_id, tenant_id, and operator_group_object_id in lab.secret.tfvars.
terraform -chdir=envs/aks init
terraform -chdir=envs/aks plan -var-file=lab.secret.tfvars -out=lab.tfplan
terraform -chdir=envs/aks apply lab.tfplan
terraform -chdir=envs/aks output -raw get_credentials_command
# Execute the printed az command, then convert kubeconfig to Entra ID login:
kubelogin convert-kubeconfig -l azurecli
```

GKE and AKS default to isolated local Terraform state per root for single-operator labs. Before collaborating across operators, configure a remote GCS or Azure Blob backend and run `terraform init -migrate-state`; never share state files or keys with EKS. Never commit `.tfstate`, `.tfplan`, `*.secret.tfvars`, or `kubeconfig` files.

Every cluster disables public Kubernetes API endpoints. Operators must run `helm`, `kubectl`, and `kubeseal` from an SSM-managed host, bastion, or VPN with private routing and DNS resolution—Terraform does not build laptop VPN tunnels. GKE enforces master authorized networks (`operator_access_cidrs`, excluding `/0`); ensure node/pod/service CIDRs do not overlap with your connected network. AKS disables local admin accounts and grants cluster admin via the configured Entra group. GKE enforces NetworkPolicy through Dataplane V2 (and opens TCP `9443` from the control plane to nodes for Kyverno admission webhooks per [Kyverno troubleshooting guidance](https://kyverno.io/docs/troubleshooting/)) using a dedicated node service account with [least-privilege GKE node roles](https://cloud.google.com/kubernetes-engine/docs/how-to/hardening-your-cluster#use_least_privilege_sa). AKS enforces NetworkPolicy with Calico.

## 4. Bootstrap the Shared GitOps Configuration

Push your fork or repository branch before bootstrapping. If publishing under a different GitHub owner, update the repository URLs in `gitops-config/bootstrap/`, `gitops-config/applicationsets/`, and `gitops-config/platform/*-app.yaml`. Register repository pull credentials in Argo CD when using a private repo, and create the cluster-bound `redis-cart` SealedSecret following `gitops-config/README.md` before syncing Boutique.

From `platform-infra`, once kubeconfig is configured for GKE or AKS:

```bash
kubectl config get-contexts
# Replace YOUR_KUBE_CONTEXT with the kube_context output from Terraform:
bash scripts/bootstrap-argocd.sh nonprod ../gitops-config YOUR_KUBE_CONTEXT managed
```

The bootstrap script passes `--kube-context` explicitly to Helm and `kubectl`. The `managed` profile selects `gitops-config/bootstrap/nonprod-managed`, which inherits `nonprod` while omitting the upstream `metrics-server` Helm chart so cloud-managed GKE/AKS metrics components are not duplicated. Omitting the third and fourth arguments preserves the standard AWS EKS bootstrap path (`nonprod` installs `dev`, `staging`, `preview`, and `GoKubeDownscaler`; `prod` targets a dedicated production cluster). Remember that on AWS EKS, routine `TF_VAR_operator_role_arn` defaults to read-only `AmazonEKSViewPolicy`, so run initial `bootstrap-argocd.sh` under the distinct `TF_VAR_break_glass_role_arn` (`AmazonEKSClusterAdminPolicy`) profile via `EKS_OPERATOR_PROFILE`.

The `platform-addons` `ApplicationSet` deploys the pinned OpenCost (`2.5.20`) and `kube-prometheus-stack` Helm charts automatically—do not install a second standalone OpenCost release. After Argo CD reconciles the platform add-ons, verify OpenCost:

```bash
kubectl --context YOUR_KUBE_CONTEXT -n argocd get applications
kubectl --context YOUR_KUBE_CONTEXT -n opencost rollout status deployment/opencost --timeout=10m
kubectl --context YOUR_KUBE_CONTEXT -n opencost port-forward svc/opencost 9003:9003
# In a second terminal:
curl --fail 'http://localhost:9003/allocation?window=1h&aggregate=namespace,label:env,label:team'
```

If `deployment/opencost` is not yet present, inspect `platform-opencost`, `platform-monitoring`, and `platform-addons` in Argo CD. If allocations are empty, confirm Prometheus targets are healthy and allow initial scrape windows to accumulate. Weekly comparisons require 14 complete UTC days. Nonproduction Prometheus uses ephemeral pod storage and loses history on pod replacement; attach durable storage before relying on recurring live reports.

## 5. AWS Athena: Provision Catalog, Results Bucket, and Reporter IRSA

This section applies to AWS billing integration. Enable a legacy Cost and Usage Report (CUR) exporting Parquet with `DAILY` or `HOURLY` granularity in the AWS Billing console, and activate user-defined cost allocation tags `team` and `env`. Terraform provisions query infrastructure over your S3 billing prefix; AWS still controls billing delivery cadence.

Add the following to your `*.secret.tfvars` for `platform-infra/bootstrap/state-backend` (or environment `cost_reporting` input):

```hcl
athena_cur_catalog = {
  database_name = "finops"
  table_name    = "cur"
  data_s3       = "s3://YOUR-CUR-BUCKET/path/to/parquet-data/"
}
athena_reporter = {
  oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/YOUR-ID"
  oidc_issuer_url   = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/YOUR-ID"
}
```

Supply the OIDC provider ARN and issuer URL of the EKS cluster running `finops-reporter` (omit `athena_reporter` if running the CLI manually under an IAM role that already has query permissions). Run `terraform plan` and `apply` against `bootstrap/state-backend` using your existing state bucket and budget inputs.

When `athena_results_s3` is left `null`, the module creates a dedicated private, KMS/SSE-encrypted, TLS-only query-results bucket, Glue database/table for legacy Parquet CUR (see [cost-reporting module README](../../platform-infra/modules/cost-reporting/README.md); CUR 2.0 / FOCUS schemas require separate table definitions or `finops cloud-report`), and an Athena workgroup enforcing a `5 GiB` per-query scan limit.

```bash
terraform -chdir=bootstrap/state-backend output -json athena_reporter_environment
terraform -chdir=bootstrap/state-backend output -raw athena_reporter_role_arn
```

Copy the output environment variables into `gitops-config/platform/finops-reporter/cronjob.yaml` and set `eks.amazonaws.com/role-arn` on the `finops-reporter` ServiceAccount. The IRSA trust policy binds strictly to `system:serviceaccount:finops:finops-reporter` with prefix-scoped read access on CUR data and read/write on query results—never modify/delete permissions on billing exports. Note that `platform/finops-reporter` is digest-pinned (`ghcr.io/workwithcrow12-art/finops-toolkit@sha256:...`), carries `team: platform` and `env: shared` Pod labels, and is validated by Kyverno in the `finops` namespace.

## 6. Multi-Cloud Billing Normalization (AWS / GCP / Azure)

Export cloud billing data to CSV following [FOCUS 1.0/1.1](https://focus.finops.org/wp-content/uploads/2024/11/FOCUS-spec-v1_1.pdf), or map native exports to the documented column subset in `finops-toolkit/README.md`. Concatenate rows into **one CSV with a single header**, keep `ProviderName` values consistent, and avoid duplicate line items.

```bash
# From finops-toolkit after running `python -m pip install .`:
finops cloud-report --input exports/combined-focus.csv --as-of 2026-01-19
```

The CLI groups spend by provider, environment, and team while keeping each `BillingCurrency` separate without FX conversion and without summing into OpenCost. Every provider present across the two-week window must have records covering all 14 UTC days: zero-cost rows and negative credits are preserved, while missing dates raise an error instead of silently assuming `$0`. Always reconcile normalized CSV inputs against upstream invoices to catch omitted providers, duplicate exports, or unfinalized billing periods.

## 7. Pre-PR Local Validation Checklist

From `platform-infra` (with Terraform `1.11.4`, Conftest `0.62.0`, and provider cache/network access):

```bash
make validate
python3 -m unittest discover -s tests -v
python3 scripts/offline_plan_check.py --output-dir .scratch/plans
```

`make validate` runs `terraform fmt -check -recursive`, `init -backend=false`, `validate`, and mocked `terraform test` suites across AWS bootstrap/`nonprod`/`prod`, GKE, AKS, and all six modules without cloud credentials. `offline_plan_check.py` generates offline Terraform JSON plans for `nonprod`, `prod`, `gke`, and `aks` so Conftest (`policies/tagging.rego`) enforces cost tags on real planned resources in `.github/workflows/terraform.yml` alongside optional Infracost PR summaries. Root `.github/workflows/terraform-apply.yml` and `terraform-drift.yml` provide opt-in OIDC plan/apply and drift workflows once repository variables and GitHub Environments are configured.

From `gitops-config`:

```bash
kyverno test platform/kyverno/tests
```

Root `.github/workflows/gitops.yml` verifies SHA-256 checksums for `kubeconform` and `kyverno`, pins `datreeio/CRDs-catalog` by commit SHA, renders all overlays and bootstrap roots, applies all four Kyverno policies to rendered Pods in both `boutique-*` and `finops`, and scans deployed Redis digests with Trivy.

From `finops-toolkit` and the monorepo root:

```bash
cd finops-toolkit
python -m pip install '.[dev]'
make lint test
cd ..
python -m unittest discover -s scripts/tests -v
```

Local mock plans, policy tests, and manifest renders catch configuration defects early, while live provider IAM/OIDC permissions, quotas, private VPC routing, controller syncs, OpenCost pricing accuracy, and real billing exports still require verification during a dedicated cloud lab run.
