# Investigate an AWS Budget or Spend Alert

AWS Budgets (provisioned via `bootstrap/state-backend`, optional in `envs/nonprod`, and **mandatory** via `var.budget` in `envs/prod`) sends email/SNS alerts when actual or forecasted spend crosses configured thresholds. Budgets do not automatically stop workloads or delete AWS resources.

## Investigation Steps

1. **Capture alert context:** Record the AWS account alias/redacted ID, budget name (`cost-aware-nonprod-monthly`, `cost-aware-prod-monthly`, or shared account budget), alert timestamp, threshold percentage, and billing period.
2. **Compare AWS billing against OpenCost separately:**
   - Group AWS Cost Explorer / Athena CUR unblended spend by AWS service (`AmazonEKS`, `AmazonEC2`, `AmazonVPC` NAT Gateway hours/GB, `AmazonCloudWatch`, `AWSKeyManagementService`) and activated cost allocation tags (`env`, `team`, `project`, `owner`).
   - Query OpenCost / `finops report` over the matching UTC dates to identify namespace or workload changes (`boutique-*`, `finops`, `monitoring`). Keep CUR and OpenCost totals separate because they cover overlapping underlying EC2/EBS resources.
   - If `finops report` or `finops cloud-report` exits on incomplete 14-day UTC coverage, check AWS CUR Parquet delivery latency and Prometheus TSDB retention before rerunning. Missing billing days are never `$0`, and an ephemeral nonprod Prometheus pod restart clears historical scrape samples.
3. **Correlate against infrastructure and GitOps changes:** Check recent merges in `platform-infra` (node counts, `nat_per_az = true` 3-NAT configuration in `prod`, interface VPC endpoints, or opt-in Karpenter settings), `gitops-config` (`downscaler/force-uptime` left enabled on `dev`/`staging`, HPA bounds, or new LoadBalancer/PVC claims), and `.github/workflows/terraform-drift.yml` summaries.
4. **Inspect waste candidates safely:** Review the latest read-only Cloud Custodian report (`.github/workflows/custodian-weekly.yml` artifact or `finops waste --dry-run`) for unattached gp3 EBS volumes (such as retained `Retain`-policy Prometheus disks), unused Elastic IPs, stale snapshots, or idle ALBs/NLBs. Verify resource ownership, active traffic, and backup requirements before deleting anything.
5. **Remediate and confirm trend:** Apply the corrective change through Terraform or GitOps PRs (or tear down idle lab clusters cleanly via `make destroy`), document the root cause, and confirm daily spend normalizes after the next 24–48 hour AWS billing refresh.
