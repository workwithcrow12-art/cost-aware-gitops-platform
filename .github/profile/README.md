# Cost-aware GitOps Platform

A portfolio lab that delivers Google's Online Boutique on AWS EKS with Terraform and Argo CD. It connects
image promotion and frontend canary checks to Kubernetes cost allocation, AWS budget alerts and weekly reports.

[Architecture](../docs/architecture/overview.md) · [Demo and measurements](../docs/case-study.md) · [Portfolio notes](../docs/portfolio.md) · [Rebuild runbook](../docs/runbooks/khoi-phuc-cluster-tu-git.md)

## Repositories

| Repository | Purpose |
|---|---|
| [platform-infra](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/tree/main/platform-infra) | Terraform for VPC, EKS, S3 state and AWS Budgets |
| [gitops-config](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/tree/main/gitops-config) | Argo CD bootstrap, Kubernetes overlays and Helm add-ons |
| [boutique-app](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/tree/main/boutique-app) | Online Boutique source and CI for testing, scanning and publishing images |
| [finops-toolkit](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/tree/main/finops-toolkit) | Python CLI for OpenCost, optional Athena billing data and Cloud Custodian findings |

## What to try

1. Render the dev, staging, prod and preview manifests with Kustomize.
2. Generate a weekly cost report and a waste summary from the committed FinOps fixtures.
3. For an AWS lab, provision nonprod and bootstrap Argo CD. Review a GitOps promotion PR and observe
   the frontend canary and its candidate health checks.

The case study distinguishes local checks, synthetic cost data and measurements that require a running cluster.
The current portfolio evidence covers local validation. AWS deployment, hosted CI and measured cost savings require recorded lab runs.

## CV bullet

> Designed and implemented a cost-aware GitOps platform for Online Boutique targeting AWS EKS with Terraform, Argo CD and GitHub Actions.
> Implemented digest-pinned image promotion, a Prometheus-gated frontend canary, and OpenCost and AWS CUR reporting.

Application code comes from [Google Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo)
under Apache 2.0. This project's work is the infrastructure, deployment automation and FinOps tooling.
