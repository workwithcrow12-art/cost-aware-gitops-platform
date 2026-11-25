# Rebuild the AWS EKS Cluster from Git

Use a dedicated AWS sandbox or target account and verify caller identity, region, and budget guardrails before creating infrastructure. EKS control planes, EC2 worker nodes, NAT Gateways, EBS volumes, KMS keys, and CloudWatch Logs accrue hourly charges while provisioned.

## 0. Run Offline Preflight and Dry-Run Evidence Setup

From the monorepo root, run the Cloud Lab Readiness Kit to check CLI binaries (`terraform`, `kubectl`, `helm`, `kubeseal`, `aws`), required environment variables, private API routing requirements, and `ap-southeast-1` `Decimal` cost estimates:

```bash
python scripts/cloud_lab_preflight.py --env nonprod --hours 2 --verify-identity --strict
python scripts/cloud_lab_runner.py --env nonprod --dry-run
```

Use the [AWS lab evidence checklist](aws-lab-evidence.md) to record timestamps, commit SHAs, and redacted logs. Note that `dev` and `staging` workloads run `08:00–20:00` on weekdays in `Asia/Ho_Chi_Minh` (`GoKubeDownscaler`). For an exercise outside that window, temporarily commit `downscaler/force-uptime: "true"` on the `boutique-dev` Namespace and revert it before finishing.

## 1. Create or Reuse the Terraform State Backend

If the AWS account does not yet have the shared S3 state backend and account-level AWS Budget, provision `bootstrap/state-backend` once from `platform-infra`:

```bash
cd platform-infra
terraform -chdir=bootstrap/state-backend init
terraform -chdir=bootstrap/state-backend apply
```

When rebuilding an existing environment, always reuse the existing state bucket and state keys rather than creating orphaned duplicate infrastructure.

## 2. Configure Least-Privilege Operator, Break-Glass Admin, and Budget Inputs

Routine cluster access (`TF_VAR_operator_role_arn`) defaults to read-only `AmazonEKSViewPolicy` (`var.operator_access_policy` supports `AmazonEKSViewPolicy` or `AmazonEKSEditPolicy`). Because initial Helm/Argo CD installation requires cluster-scoped RBAC and CRD creation, also supply a distinct IAM role ARN via `TF_VAR_break_glass_role_arn`, which grants `AmazonEKSClusterAdminPolicy` for bootstrap and emergency break-glass recovery.

From `platform-infra`:

```bash
export STATE_BUCKET="$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_name)"
export STATE_BUCKET_REGION="$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_region)"
export TF_VAR_operator_role_arn='arn:aws:iam::123456789012:role/ClusterOperatorView'
export TF_VAR_break_glass_role_arn='arn:aws:iam::123456789012:role/ClusterBreakGlassAdmin'
export TF_VAR_operator_access_cidrs='["10.20.1.0/24"]'

# Required when ENV=prod (optional but recommended in nonprod):
# export TF_VAR_budget='{"monthly_limit_usd":500,"email":"finops@example.com"}'

make plan ENV=nonprod
make apply ENV=nonprod
```

> **Production note (`ENV=prod`):** `platform-infra/envs/prod` requires a non-null `TF_VAR_budget` (`monthly_limit_usd > 0` and notification `email`) and defaults `nat_per_az = true` (`3 × $0.059/hr` NAT Gateways in `ap-southeast-1`, `~$127–$129/month` fixed baseline before per-GB charges; set `TF_VAR_nat_per_az=false` only if explicitly trading multi-AZ egress isolation for lower fixed NAT cost). Alternatively, trigger root `.github/workflows/terraform-apply.yml` once OIDC roles, `vars.TF_PROD_BUDGET_JSON`, and GitHub Environment reviewers are configured.

## 3. Bootstrap Argo CD over the Private EKS Endpoint

Run `bootstrap-argocd.sh` from a host inside the VPC (for example, an SSM Session Manager host) or over VPN with routed access and private DNS resolution matching `TF_VAR_operator_access_cidrs`. Authenticate `EKS_OPERATOR_PROFILE` as the `TF_VAR_break_glass_role_arn` role so Helm and `kubectl` have `AmazonEKSClusterAdminPolicy` during initial installation:

```bash
export EKS_OPERATOR_PROFILE='break-glass-admin'
bash scripts/bootstrap-argocd.sh nonprod ../gitops-config
kubectl -n argocd get applications,applicationsets
```

After bootstrap completes, switch day-to-day inspection sessions back to the least-privilege `TF_VAR_operator_role_arn` profile.

## 4. Seal Cluster Credentials and Run the Storefront Checkout Smoke Test

Generate and commit the cluster-bound `redis-cart` SealedSecret for `dev` following [gitops-config/README.md](../../../gitops-config/README.md). Overlays in `gitops-config/apps/boutique/overlays/{dev,staging,prod,preview}` already pin verified `v0.9` GHCR `@sha256` digests. Once `boutique-dev` reconciles to `Healthy`, start a local port-forward:

```bash
kubectl -n boutique-dev get rollout frontend
kubectl -n boutique-dev port-forward svc/frontend 8080:8080
```

In a second terminal from the monorepo root, execute the automated smoke stage via `cloud_lab_runner.py` (which records UTC start/end timestamps and redacts account IDs/ARNs/tokens from saved logs) or invoke `smoke-checkout.py` directly:

```bash
python scripts/cloud_lab_runner.py --env nonprod --execute-stage smoke --base-url http://localhost:8080
# Equivalent direct smoke command:
python boutique-app/.github/scripts/smoke-checkout.py --base-url http://localhost:8080
```

This places one synthetic order through the mock payment and email services and verifies cart clearing.

## 5. Record Recovery Timing and Tear Down Disposable Labs

Record the Terraform start timestamp, Argo CD bootstrap completion timestamp, and first passing checkout smoke response to measure end-to-end cluster rebuild time. For disposable lab runs, clean up Kubernetes-created LoadBalancers and PVCs first, then follow the teardown procedure in [platform-infra/README.md](../../../platform-infra/README.md#tear-down).
