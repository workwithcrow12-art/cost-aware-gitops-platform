# platform-infra

Terraform provisions the AWS foundation for the Cost-aware GitOps Platform. The environments share VPC and EKS modules and use separate state objects and cluster names.

Optional nonprod roots in `envs/gke` and `envs/aks` provision private GKE/AKS labs with network-policy enforcement and cost labels/tags. They use separate local state by default and do not share the EKS apply/drift workflows. See the [Vietnamese quick-start](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/blob/main/.github/docs/quick-start.md) for inputs, authentication, private-network access and the shared GitOps bootstrap.

| Environment | Network | EKS system node group |
|---|---|---|
| `nonprod` | Two availability zones, one shared NAT gateway | Two Spot nodes for dev, staging and optional previews |
| `prod` | Three availability zones, one NAT gateway per zone | Three On-Demand nodes for production |

Both environments use private worker subnets and private-only Kubernetes API endpoints. VPC Flow Logs capture accepted and rejected traffic in CloudWatch. The state bootstrap creates a versioned S3 bucket with an HTTPS-only policy, an account-wide AWS Budget and, when configured, GitHub OIDC roles and an Athena workgroup.

## Validate locally

Run from this repository in a Bash-compatible shell with GNU Make and Terraform. Validation uses the locked AWS, Google and Azure providers, disables remote backends and runs mocked Terraform tests for every root and the reporting module. It needs provider downloads but no cloud credentials.

```bash
make validate
python3 -m unittest discover -s tests -v
conftest verify --policy policies
```

## Deploy an AWS lab

Use an AWS sandbox account with an AWS CLI session and permissions to create the documented resources. Install Terraform, kubectl and Helm at the versions in `.tool-versions`. Set an AWS Budget alarm before creating chargeable resources. EKS, NAT gateways, EC2 and logging incur charges while the lab runs.

```bash
# Bootstrap shared state and the monthly budget once per account.
terraform -chdir=bootstrap/state-backend init
terraform -chdir=bootstrap/state-backend apply

export STATE_BUCKET=$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_name)
export STATE_BUCKET_REGION=$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_region)

# Replace these examples with your operator role and routed private source ranges.
export TF_VAR_operator_role_arn='arn:aws:iam::123456789012:role/EKSOperator'
export TF_VAR_operator_access_cidrs='["10.50.0.0/24"]'

make plan ENV=nonprod
make apply ENV=nonprod

# Run Kubernetes bootstrap from the VPC or a connected private network.
bash scripts/bootstrap-argocd.sh nonprod ../gitops-config
```

The bootstrap prompts for a globally unique bucket name, the budget amount in USD and a notification email. Keep the bootstrap's local state in a protected location. The environment roots use S3 lockfiles and default to `ap-southeast-1`. Set `TF_VAR_aws_region` to choose another region.

The operator host must be able to resolve and route to the private endpoint. Use a host inside the VPC, for example an EC2 instance managed through Systems Manager, or a privately connected network with working DNS resolution and return routes. The cluster security group grants TCP 443 to `operator_access_cidrs`, so supply the host's private CIDR or the connected source range. The Terraform GitHub jobs use AWS service APIs and can run on hosted runners. The Helm and kubectl bootstrap requires the private path.

The GitOps checkout must contain the bootstrap project, root app and Helm values from the revision Argo CD will fetch. Update repository URLs and revisions in your GitOps checkout and push them before bootstrapping a fork. The script chooses `bootstrap/nonprod` or `bootstrap/prod` and uses the EKS cluster ARN as the kubeconfig context.

New clusters give Kubernetes administrator access to the explicitly configured operator role. Run bootstrap as that role or set `EKS_OPERATOR_PROFILE` to its AWS CLI profile. The profile must be able to describe the cluster and acquire a Kubernetes authentication token. Terraform still uses its own AWS credentials to read the environment outputs.

See the [EKS migration steps](modules/cluster/README.md#migrate-an-existing-cluster) before applying these changes to an existing cluster.

## Tear down

```bash
make destroy ENV=nonprod
```

Use the same AWS account, state bucket and Terraform inputs as the deployment. Clean up any Kubernetes-managed cloud load balancers and persistent volumes before destroying the cluster. The shared state bucket and budget are managed separately from either environment.

## GitHub Actions

| Workflow | What it does |
|---|---|
| `terraform-pr.yml` | Runs Terraform formatting, TFLint, validation, mocked plans and cost-tag policy tests. It uses a read-only GitHub token. |
| `terraform-apply.yml` | Creates a policy-checked plan on `main`, retains it for review, then applies that exact plan after the environment approval. |
| `drift-detection.yml` | Runs read-only refresh plans, fails on drift, and retains a seven-day summary of changed resource addresses/actions without state values. |

To enable the AWS jobs, configure GitHub's immutable OIDC subject template and pass the repository names, IDs and IAM permission policy ARNs to the state bootstrap. See the [OIDC module](modules/iam-github-oidc/README.md) for the template and permission requirements. The AWS role trust binds each job to its workflow file on `main`.

Set these GitHub repository variables:

| Variable | Value |
|---|---|
| `TF_STATE_BUCKET`, `TF_STATE_REGION` | State bootstrap outputs |
| `AWS_REGION` | Region where the clusters run, defaults to `ap-southeast-1` |
| `AWS_ACCOUNT_ID` | Expected AWS account for GitHub's role assumption |
| `AWS_PLAN_ROLE_ARN` | `plan` role from `github_role_arns` |
| `EKS_OPERATOR_ACCESS_CIDRS` | JSON list of routed operator IPv4 CIDRs for the private endpoint |
| `EKS_OPERATOR_ROLE_ARN` | The human operator's IAM role ARN |
| `TF_DRIFT_ENABLED` | Set to `true` once both environment states exist |

Create GitHub environments named `nonprod` and `prod`. Set each environment's `AWS_APPLY_ROLE_ARN` variable to its deployment role and restrict deployments to `main`. Configure required reviewers on `prod` where your GitHub plan supports it.

The plan job uses repository-level settings and `AWS_PLAN_ROLE_ARN` before any
environment approval. Update the bootstrap's plan-role trust to include this
workflow, and give it state-lockfile permissions as documented in the OIDC module.
Review the artifact's `plan.txt` and commit SHA before approving the apply job.
Configure required reviewers and prevent self-review for each environment that
requires approval; YAML alone cannot enforce GitHub account settings. Without
those settings, the apply job starts automatically after planning.

The binary plan may contain sensitive state even when the text view redacts it.
Restrict repository/artifact access accordingly; both expire after one day. Apply
downloads the artifact by ID, checks the plan SHA-256 from the plan job and rejects
plans older than 24 hours. Terraform also rejects plans made against stale state.
After expiry or state changes, dispatch and review a new run. Never apply a new
unreviewed plan as a fallback. Run `make lint` locally with TFLint 0.61.0.

Production enables the EBS CSI managed add-on with a dedicated ServiceAccount-
bound IRSA role and AWS's `AmazonEBSCSIDriverPolicyV2`. GitOps supplies the encrypted
gp3 StorageClass and persistent Prometheus claim. Add the CSI role to the apply
role's reviewed `iam:PassRole` permissions. Nonprod leaves the add-on disabled.

## FinOps data

The AWS provider supplies `team`, `env`, `project` and `owner` default tags. The same environment tag map is applied to worker EC2 instances and EBS volumes through a launch template. Conftest checks the resulting `tags_all` on supported managed resources changed by a plan. Activate the relevant user-defined cost allocation tags in Billing to include them in AWS cost reports. Existing node groups require replacement; follow the [worker cost-tag migration](modules/cluster/README.md#migrate-worker-cost-tags) before applying.

Use the existing Infracost project config to estimate changes locally with an authenticated Infracost CLI.

```bash
infracost breakdown --config-file infracost.yml
```

For optional AWS spend reporting, set `athena_cur_catalog` on the shared bootstrap to create a Glue database/table over an existing legacy CUR Parquet prefix and a private encrypted query-results bucket. Add `athena_reporter` to provision a scoped IRSA role for the reporting CronJob. Existing callers can keep `athena_results_s3` for workgroup-only provisioning. All modes enforce a 5 GiB per-query scan cap. See the [reporting module](modules/cost-reporting/README.md) for inputs, schema requirements and runtime outputs.

The managed node groups have fixed Terraform node counts. Karpenter and AWS Cost Anomaly Detection are future extensions.
