# AWS Nonprod Lab Prerequisites and Evidence Runbook

## Current Execution Status (Baseline Record: 2026-11-16)

**No live cloud lab has been executed from this repository workspace; zero AWS resources were provisioned.** An earlier request asked for a strictly `$0` Free Tier run on a host without AWS CLI, Terraform, `kubectl`, `helm`, `kubeseal`, active AWS credentials, or private VPC routing.

Provisioning `envs/nonprod` creates an EKS control plane, two `m6i.large`/`m6a.large`/`m5.large` Spot worker nodes, one shared NAT Gateway, gp3 EBS root volumes, KMS encryption keys, and CloudWatch Logs. **An "AWS Free Tier" account label never guarantees a `$0` invoice for this architecture:**

- [Amazon EKS pricing](https://aws.amazon.com/eks/pricing/) bills `$0.10` per cluster per hour for Standard support, before worker EC2 instances, NAT Gateways, storage, or logs.
- [AWS Free Tier](https://aws.amazon.com/free/) distinguishes promotional credit/time-bounded Free plans from Paid plans; individual service free tiers or credits must be verified directly in the target account's AWS Billing console before `terraform apply`.
- AWS Budgets sends email/SNS alerts after actual or forecasted spend crosses thresholds—it does **not** hard-cap charges or terminate running resources automatically.

Until account billing eligibility, credits/budget approval, and private VPC connectivity are confirmed, use the zero-credential [5-minute offline demo](../demo.md) and the offline Cloud Lab Readiness Kit (`scripts/cloud_lab_preflight.py` and `scripts/cloud_lab_runner.py --dry-run`).

## Turnkey Preflight & Dry-Run Kit

Before running any cloud command, inspect local CLI availability, required environment variables, private EKS API reachability warnings, and itemized `ap-southeast-1` `Decimal` cost estimates from the monorepo root:

```bash
# Offline readiness report + 2-hour session & 30-day Decimal cost table (zero network calls):
python scripts/cloud_lab_preflight.py --env nonprod --hours 2

# Optional live AWS STS caller check once credentials are configured:
python scripts/cloud_lab_preflight.py --env nonprod --hours 2 --verify-identity --strict

# Generate a fresh dry-run execution plan and NOT RUN evidence template under .scratch/:
python scripts/cloud_lab_runner.py --env nonprod --dry-run
```

For production readiness checks (`--env prod`), `cloud_lab_preflight.py` additionally enforces `TF_VAR_budget` because `platform-infra/envs/prod` requires a non-null monthly AWS Budget and models 3 AZ NAT Gateways (`nat_per_az = true`, `3 × $0.059/hr`).

## Pre-Provisioning Verification Checklist

Record your checks in a local `.scratch/aws-lab-<timestamp>` folder (gitignored). **Never commit access keys, session tokens, unredacted 12-digit AWS account IDs, IAM ARNs, binary `.tfplan` files, `.tfstate`, or plaintext secret manifests:**

| Prerequisite | What to verify before `terraform apply` |
| --- | --- |
| Identity | Active sandbox AWS CLI session; `aws sts get-caller-identity --profile "$EKS_OPERATOR_PROFILE"` resolves to the intended disposable sandbox account. |
| Cost & credits | Account plan type, active promotional credits and expiration date, target region (`ap-southeast-1`), planned runtime window, and itemized EKS/EC2/NAT/EBS/KMS/CloudWatch/egress estimates via `cloud_lab_preflight.py`. Stop immediately if `$0` out-of-pocket spend is required without verified credit coverage. |
| Budget & teardown | Explicit spending limit approved by the account owner, configured AWS Budget alert recipient, and scheduled teardown time. |
| Terraform state | Reuse existing `bootstrap/state-backend` S3 bucket (`STATE_BUCKET`) if already created in the account; never create duplicate clusters during recovery drills. |
| Least-privilege & break-glass roles | Routine `TF_VAR_operator_role_arn` defaults to read-only `AmazonEKSViewPolicy`. Configure a distinct `TF_VAR_break_glass_role_arn` (`AmazonEKSClusterAdminPolicy`) for initial `bootstrap-argocd.sh` installation and emergency cluster admin tasks, plus routed private `TF_VAR_operator_access_cidrs` (excluding `/0`) from an SSM host, bastion, or VPN with private VPC DNS resolution. |
| Desired state in Git | Target Git revision pushed to the repository URL read by Argo CD; GHCR package pull visibility verified; cluster-bound `redis-cart` SealedSecret prepared for `boutique-dev` without logging plaintext secrets. |
| Local toolchain | `aws`, `bash`, `make`, `kubeseal`, `git`, Python 3.11+, and `terraform` (`1.11.4`), `kubectl` (`1.35.0`), and `helm` (`3.18.6`) matching `platform-infra/.tool-versions`. |

Note: Provisioning, storefront checkout, canary fault injection, rollback, and teardown can all be measured within a single 2-hour lab session. Generating a live weekly `finops report` comparison requires 14 complete UTC days of billing/metrics retention and incurs multi-week infrastructure charges.

## Live Execution Steps and Required Evidence

From the monorepo root, initialize a fresh evidence directory with `python scripts/cloud_lab_runner.py --env nonprod --dry-run` (or execute live non-destructive verification stages with `--execute-stage preflight` / `--execute-stage smoke`, which automatically redacts 12-digit AWS account IDs, ARNs, tokens, and secrets from saved logs).

1. **Provision `nonprod` infrastructure:** Follow [cluster rebuild from Git](khoi-phuc-cluster-tu-git.md) from `platform-infra` to create or reuse the state backend, review `make plan ENV=nonprod`, and apply the reviewed configuration. Record UTC start/end timestamps, region, and exit codes; abort immediately if account identity or planned resources diverge from expectations.
2. **Bootstrap Argo CD over the private EKS API:** From your connected VPC host/VPN authenticated as `TF_VAR_break_glass_role_arn` (`EKS_OPERATOR_PROFILE`), run `bash scripts/bootstrap-argocd.sh nonprod ../gitops-config`. Record the bootstrap root (`gitops-config/bootstrap/nonprod`), Git SHA, and `kubectl -n argocd get applications,applicationsets`. Seal and sync `redis-cart` for `boutique-dev`, then wait for all Boutique workloads to report `Healthy`.
3. **Verify baseline checkout smoke:** Record active `ghcr.io/workwithcrow12-art/*@sha256:...` digests and `kubectl -n boutique-dev get rollouts,analysisruns,pods`. Port-forward `svc/frontend 8080:8080` and run `--execute-stage smoke` (or `python boutique-app/.github/scripts/smoke-checkout.py --base-url http://localhost:8080`). Retain the exit code and synthetic order confirmation (mock payment/email services only—never enter real payment card numbers).
4. **Execute canary auto-abort drill (`dev` only):** Follow [canary rollback exercise](../postmortems/001-canary-tu-rollback.md) by merging a GitOps PR on `dev` setting the candidate frontend's `PRODUCT_CATALOG_SERVICE_ADDR` to `missing-catalog:3550`. Record the merged PR SHA, Rollout start time, and `AnalysisRun` failure timestamp, verifying that stable pods continue serving traffic. Record actual behavior faithfully if results differ.
5. **Restore desired state via Git revert:** Follow [manual rollback](rollback-thu-cong.md) to revert the bad GitOps commit via PR, wait for Argo CD reconciliation, rerun `smoke-checkout.py`, and record restored digests and timestamps. Remove `downscaler/force-uptime` if it was temporarily added.
6. **Clean up Kubernetes cloud resources and destroy lab:** Inspect and remove any Kubernetes-provisioned LoadBalancers or PVCs before running `make destroy ENV=nonprod` from `platform-infra` (retain `bootstrap/state-backend` to preserve state history). Verify zero residual EKS clusters, EC2 instances, NAT Gateways, unattached EBS volumes, Elastic IPs, or log streams remain in the region, and recheck AWS Billing after billing data refreshes (`terraform destroy` exit `0` alone does not prove a `$0` final bill).

## Evidence Table Template

Copy or generate this table via `python scripts/cloud_lab_runner.py --dry-run` and update rows only with timestamped logs from an actual run—never replace `NOT RUN` with projected outcomes:

| Stage | UTC Start / End | Commit / Digest | Result / Log Path |
| --- | --- | --- | --- |
| Identity, preflight & cost check | — | — | NOT RUN |
| Terraform plan/apply (`nonprod`) | — | — | NOT RUN |
| Argo CD private-API bootstrap healthy | — | — | NOT RUN |
| Pre-drill storefront checkout smoke | — | — | NOT RUN |
| Canary fault drill & stable availability | — | — | NOT RUN |
| Git revert rollback & post-rollback smoke | — | — | NOT RUN |
| Teardown & residual-resource check | — | — | NOT RUN |
| Post-refresh AWS Billing reconciliation | — | — | NOT RUN |

Calculate recovery time from fault detection to successful post-rollback checkout, reporting continuous stable-pod availability separately from Git desired-state restoration time. Publish measurements only alongside their corresponding redacted logs and UTC timestamps.
