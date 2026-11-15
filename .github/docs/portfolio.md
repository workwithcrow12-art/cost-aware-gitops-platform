# Portfolio and CV notes

## Project summary

**Cost-aware GitOps Platform — AWS EKS, Terraform, Argo CD, GitHub Actions, Python**

Designed and implemented a portfolio platform that connects image delivery, Kubernetes deployment policies and cloud cost reporting. The lab deploys Google's Online Boutique, with separate nonprod and prod infrastructure and a reviewed GitOps release flow.

This version is intended for code review, a local demo and an interview walkthrough. See the [verification record](case-study.md) for exactly what was executed. Live AWS operation and measured savings are not claimed.

## CV wording

English:

- Built a Terraform and Argo CD platform targeting AWS EKS, with separate environments, digest-pinned image promotion, frontend canary checks and Kubernetes admission/network policies.
- Implemented a Python FinOps CLI comparing OpenCost allocation with optional AWS CUR/Athena data, rejecting incomplete reporting periods and summarizing read-only Cloud Custodian findings.
- Added automated service and checkout tests, infrastructure mock plans, policy validation and operational runbooks for deployment, rollback and cost investigation.

Tiếng Việt:

- Xây dựng nền tảng GitOps hướng tới AWS EKS bằng Terraform và Argo CD, tách môi trường, triển khai image theo digest, kiểm tra canary cho frontend và áp dụng chính sách Kubernetes.
- Phát triển CLI Python tổng hợp chi phí OpenCost và AWS CUR/Athena, phát hiện kỳ báo cáo thiếu dữ liệu và tổng hợp tài nguyên có khả năng lãng phí.
- Bổ sung kiểm thử dịch vụ và checkout, kiểm thử hạ tầng bằng mock plan, kiểm tra policy và tài liệu triển khai, rollback, điều tra chi phí.

Attribute the application to Google Online Boutique. Describe your contribution as platform engineering, delivery automation, FinOps and verification. Do not describe the fixture percentages as achieved savings, claim production uptime or claim a live deployment without the corresponding run evidence.

## Five-minute walkthrough

1. Explain the [architecture](architecture/overview.md): application source, image registry, desired-state repository, Argo CD, EKS and separate billing sources.
2. Follow the [local demo](case-study.md#run-the-local-checks) and show the [weekly cost report](evidence/weekly-report.md). Explain why AWS billing and Kubernetes allocation are not added together.
3. Show a service test and the checkout integration test in `boutique-app`, then explain the distinction between local dependency tests and a deployed storefront smoke test.
4. Walk through the release flow: scanned images, complete digest record, reviewed config PR, candidate probe and explicit desired-state rollback.
5. Describe the lab's limits and the measurements needed to establish deployment success and real cost impact.

## Decisions to discuss

| Decision | Reason and tradeoff |
|---|---|
| Separate application and desired-state repositories | Reviews make the deployed image set explicit; promotion spans repositories. |
| Helm for add-ons, Kustomize for application environments | Reuse upstream charts while keeping application patches reviewable. |
| Canary only for frontend | Demonstrates controlled delivery without inventing service-mesh routing for every backend. Replica weights are approximate. |
| Digests plus admission policies | Deployment records identify immutable images; application image publication and external Redis scanning have separate checks. |
| Fixed Spot nonprod and On-Demand prod node groups | Keeps the lab understandable; workload downscaling does not automatically remove EC2 nodes or guarantee lower AWS bills. |
| Separate OpenCost and CUR totals | Workload allocation and AWS billing overlap and have different data delays. Missing-day checks reduce misleading comparisons. |
| Ephemeral lab storage | Simplifies setup; Redis carts and Prometheus history can be lost when Pods are replaced. |

The [architecture decision records](adr/) document the choices in more detail.

## Before sharing a repository link

The local component repositories currently have no configured remotes. Choose the GitHub owner, update the repository URLs and CODEOWNERS to the actual account/team, then publish the appropriate repositories. Use the organization `.github/profile/README.md` only for an organization of that name; for a personal account, use the repository README as the landing page.

For hosted CI, configure the repository protections, environments and variables described by each README. The AWS and promotion jobs need those settings; local workflow lint is not evidence that hosted Actions ran. Link the actual published repository from the CV and retain the verification record alongside it.

Publishing or deploying is not required to rerun the offline demo. No external resources or credentials are needed for the fixture tests.
