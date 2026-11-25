# platform-infra

Terraform provisions the AWS foundation for the Cost-aware GitOps Platform. The environments share VPC and EKS modules and use separate state objects and cluster names.

Optional nonprod roots in `envs/gke` and `envs/aks` provision private GKE/AKS labs with network-policy enforcement and cost labels/tags. They use separate local state by default and do not share the EKS apply/drift workflows. See the [quick-start guide](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/blob/main/.github/docs/quick-start.md) for inputs, authentication, private-network access and the shared GitOps bootstrap.

| Environment | Network | EKS system node group | Monthly AWS Budget |
|---|---|---|---|
| `nonprod` | Two availability zones, one shared NAT gateway (`nat_per_az = false`) | Two Spot nodes for dev, staging and optional previews | Optional (`var.budget`, default `null`) |
| `prod` | Three availability zones, `nat_per_az = true` by default (one NAT gateway per zone) | Three On-Demand nodes for production | Required (`var.budget`, `nullable = false`) |

Both environments use private worker subnets, free S3 Gateway VPC endpoints (with optional ECR/STS/Logs interface endpoints), KMS-encrypted Kubernetes Secrets and CloudWatch Logs, encrypted worker gp3 root volumes, and private-only Kubernetes API endpoints. VPC Flow Logs capture accepted and rejected traffic in CloudWatch.

### Cost and access governance highlights

- **Mandatory production budget (`envs/prod`):** `var.budget` (`monthly_limit_usd > 0` and valid notification `email`) is required in `prod` so production infrastructure cannot be planned or applied without an `env=prod` tag-filtered AWS Budget alarm (80% actual and 100% forecasted thresholds).
- **Least-privilege operator RBAC + break-glass admin (`modules/cluster`):** `operator_role_arn` receives routine cluster visibility via `operator_access_policy` (`AmazonEKSViewPolicy` by default, or `AmazonEKSEditPolicy`). Cluster-wide `AmazonEKSClusterAdminPolicy` is reserved for an optional, distinct `break_glass_role_arn` used only for initial Argo CD bootstrap and emergency recovery.
- **Production NAT Gateway cost trade-off (`envs/prod`):** `nat_per_az` defaults to `true` in `prod` for AZ-isolated egress across three AZs. In `ap-southeast-1`, three NAT gateways incur ~$0.059/hr × 3 ≈ $129/month fixed before $0.059/GB data processing, compared with ~$43/month for `nat_per_az = false` (a single NAT gateway, which introduces cross-AZ data transfer charges and a single-AZ failure blast radius).

## Validate locally

Run from the monorepo's `platform-infra` directory in a Bash-compatible shell with GNU Make, Python 3.11+, and Terraform. Validation uses the locked AWS, Google and Azure providers, disables remote backends, runs mocked Terraform tests for every root and module, and generates real credential-free `terraform show -json` plans across `nonprod`, `prod`, `gke`, and `aks` for Conftest cost-tag enforcement:

```bash
make validate
python3 -m unittest discover -s tests -v
python3 scripts/offline_plan_check.py --output-dir /tmp/tf-plans
conftest verify --policy policies
conftest test /tmp/tf-plans/nonprod.json /tmp/tf-plans/prod.json /tmp/tf-plans/gke.json /tmp/tf-plans/aks.json --policy policies
```

`scripts/offline_plan_check.py` starts a local `127.0.0.1` HTTP stub answering AWS STS/EC2/EKS discovery calls and Azure local MSI token requests, stages each root without remote state backends, enables optional FinOps/Karpenter/OIDC/endpoint/break-glass modules so every tagged resource type in `policies/tagging.rego` is exercised, and verifies non-empty `resource_changes` in every output plan JSON.

## Deploy an AWS lab

Use an AWS sandbox account with an AWS CLI session and permissions to create the documented resources. Install Terraform, kubectl and Helm at the versions in `.tool-versions`. Set an AWS Budget alarm before creating chargeable resources. EKS, NAT gateways, EC2 and logging incur charges while the lab runs.

```bash
# Bootstrap shared state and the monthly budget once per account.
terraform -chdir=bootstrap/state-backend init
terraform -chdir=bootstrap/state-backend apply

export STATE_BUCKET=$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_name)
export STATE_BUCKET_REGION=$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_region)

# Routine read-only operator role + distinct break-glass admin role for initial Argo CD bootstrap.
export TF_VAR_operator_role_arn='arn:aws:iam::123456789012:role/EKSOperator'
export TF_VAR_break_glass_role_arn='arn:aws:iam::123456789012:role/EKSBreakGlassAdmin'
export TF_VAR_operator_access_cidrs='["10.50.0.0/24"]'

# Required when ENV=prod:
export TF_VAR_budget='{"monthly_limit_usd":500,"email":"finops@example.com"}'

make plan ENV=nonprod
make apply ENV=nonprod

# Run initial Kubernetes bootstrap from the VPC or a connected private network using the break-glass admin profile.
EKS_OPERATOR_PROFILE=break-glass bash scripts/bootstrap-argocd.sh nonprod ../gitops-config
```

The bootstrap prompts for a globally unique bucket name, the budget amount in USD and a notification email. Keep the bootstrap's local state in a protected location. The environment roots use S3 lockfiles and default to `ap-southeast-1`. Set `TF_VAR_aws_region` to choose another region.

The operator host must be able to resolve and route to the private endpoint. Use a host inside the VPC, for example an EC2 instance managed through Systems Manager, or a privately connected network with working DNS resolution and return routes. The cluster security group grants TCP 443 to `operator_access_cidrs`, so supply the host's private CIDR or the connected source range.

The GitOps checkout must contain the bootstrap project, root app and Helm values from the revision Argo CD will fetch. Update repository URLs and revisions in your GitOps checkout and push them before bootstrapping a fork. The script chooses `bootstrap/nonprod` or `bootstrap/prod` and uses the EKS cluster ARN as the kubeconfig context.

Because routine `operator_role_arn` access defaults to `AmazonEKSViewPolicy`, run initial Argo CD bootstrap with `TF_VAR_break_glass_role_arn` configured and `EKS_OPERATOR_PROFILE` pointing to that break-glass role's AWS CLI profile. After Argo CD manages cluster state from Git, `TF_VAR_break_glass_role_arn` can be unset or retained strictly for audited emergency recovery. See the [EKS migration steps](modules/cluster/README.md#migrate-an-existing-cluster) before applying these changes to an existing cluster.

## Tear down

```bash
make destroy ENV=nonprod
```

Use the same AWS account, state bucket and Terraform inputs as the deployment. Clean up any Kubernetes-managed cloud load balancers and persistent volumes before destroying the cluster. The shared state bucket and budget are managed separately from either environment.

## GitHub Actions

The active monorepo validation workflow is root `.github/workflows/terraform.yml`, called by `ci.yml`. It runs `make validate`, TFLint (`make lint`), unit tests (`make test`), `conftest verify`, offline multi-cloud plan generation (`scripts/offline_plan_check.py`) with `conftest test` tag-policy enforcement, and an Infracost breakdown summary when `INFRACOST_API_KEY` is configured.

Opt-in root operational workflows in `.github/workflows/` support OIDC-authenticated deployment and drift detection when repository variables are configured:

| Workflow | What it does |
|---|---|
| `terraform.yml` | Runs Terraform formatting, validation, mocked tests, TFLint, unit tests, offline plan `conftest test` gates, and optional Infracost summary. |
| `terraform-apply.yml` | Creates a policy-checked plan on `main`, retains it for review, then applies that exact plan after GitHub Environment approval. |
| `terraform-drift.yml` | Runs read-only refresh plans, fails on drift, and retains a seven-day summary of changed resource addresses/actions without state values. |

Configure GitHub's immutable OIDC subject template and pass the repository names, IDs and IAM permission policy ARNs to the state bootstrap. See the [OIDC module](modules/iam-github-oidc/README.md) for the template and permission requirements.

Set these GitHub repository variables when enabling `terraform-apply.yml` and `terraform-drift.yml`:

| Variable | Value |
|---|---|
| `TF_STATE_BUCKET`, `TF_STATE_REGION` | State bootstrap outputs |
| `AWS_REGION` | Region where the clusters run, defaults to `ap-southeast-1` |
| `AWS_ACCOUNT_ID` | Expected AWS account for GitHub's role assumption |
| `AWS_PLAN_ROLE_ARN` | `plan` role from `github_role_arns` |
| `EKS_OPERATOR_ACCESS_CIDRS` | JSON list of routed operator IPv4 CIDRs for the private endpoint |
| `EKS_OPERATOR_ROLE_ARN` | Routine operator IAM role ARN (`AmazonEKSViewPolicy` by default) |
| `EKS_BREAK_GLASS_ROLE_ARN` | Optional distinct break-glass IAM role ARN (`AmazonEKSClusterAdminPolicy`) |
| `TF_PROD_BUDGET_JSON` | Required JSON object for `prod` `var.budget` (for example `{"monthly_limit_usd":500,"email":"finops@example.com"}`) |
| `TF_DRIFT_ENABLED` | Set to `true` once both environment states exist |

Create GitHub environments named `nonprod` and `prod`. Set each environment's `AWS_APPLY_ROLE_ARN` variable to its deployment role and restrict deployments to `main`. Configure required reviewers and prevent self-review on `prod` where your GitHub plan supports it; YAML alone cannot enforce GitHub account settings.

The binary plan may contain sensitive state even when the text view redacts it. Restrict repository/artifact access accordingly; both expire after one day. Apply downloads the artifact by ID, checks the plan SHA-256 from the plan job and rejects plans older than 24 hours. After expiry or state changes, dispatch and review a new run. Run `make lint` locally with TFLint 0.61.0.

Both `nonprod` and `prod` enable the EBS CSI managed add-on by default with a dedicated ServiceAccount-bound IRSA role (`eks-cluster-name` principal tag, `k8sTagClusterId`, and AWS's `AmazonEBSCSIDriverEKSClusterScopedPolicy`). GitOps supplies the encrypted gp3 StorageClass and persistent Prometheus claim in `prod`. Add the CSI role to the apply role's reviewed `iam:PassRole` permissions.

## FinOps data

The AWS provider supplies `team`, `env`, `project` and `owner` default tags. The same environment tag map is applied to worker EC2 instances and EBS volumes through a launch template. Conftest checks the resulting `tags_all` (plus GCP labels and Azure tags) on supported managed resources changed by a plan. Activate the relevant user-defined cost allocation tags in Billing to include them in AWS cost reports. Existing node groups require replacement; follow the [worker cost-tag migration](modules/cluster/README.md#migrate-worker-cost-tags) before applying.

Use `infracost.yml` (pre-populated with deterministic `terraform_vars` across `aws-nonprod`, `aws-prod`, `gcp-gke`, and `azure-aks`) to estimate changes locally with an authenticated Infracost CLI:

```bash
infracost breakdown --config-file infracost.yml
```

For optional AWS spend reporting, set `athena_cur_catalog` on the shared bootstrap to create a Glue database/table over an existing legacy CUR Parquet prefix and a private encrypted query-results bucket. Add `athena_reporter` to provision a scoped IRSA role for the reporting CronJob. Existing callers can keep `athena_results_s3` for workgroup-only provisioning. All modes enforce a 5 GiB per-query scan cap. See the [reporting module](modules/cost-reporting/README.md) for inputs, schema requirements and runtime outputs.

The managed node groups use fixed Terraform node counts by default; `modules/karpenter` provides opt-in Karpenter IAM and interruption infrastructure (`enable_karpenter = true`), while AWS Cost Anomaly Detection remains a future extension.
