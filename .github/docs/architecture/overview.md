# Platform architecture

```mermaid
flowchart LR
    App["boutique-app"] -->|CI: test, build and scan| CI["Validated images"]
    CI -->|v0.9 publication only| GHCR["GitHub Container Registry"]
    GHCR -->|Operator reviews digests and opens PR| Config["gitops-config directory"]
    Infra["platform-infra"] -->|Terraform| EKS
    Infra --> State["S3 Terraform state"]
    Infra --> Budget["AWS Budgets"]
    Config -->|Reconcile desired state| Argo["Argo CD"]
    subgraph EKS["AWS EKS"]
        Argo --> Boutique["Online Boutique namespaces"]
        GHCR --> Boutique
        Boutique --> Rollouts["Frontend canary"]
        Prometheus["Prometheus HTTP probe"] --> Rollouts
        Boutique --> OpenCost
    end
    OpenCost --> Report["finops-toolkit"]
    Athena["Athena with an existing CUR table"] --> Report
```

Terraform creates separate EKS environments for nonprod and prod. The nonprod cluster hosts dev,
staging and eligible pull request previews. Argo CD reads a cluster-specific bootstrap path so a
nonprod installation cannot accidentally reconcile the production overlay through its normal generator.

All four components are directories of one monorepo. Root workflows are active; nested workflows are standalone examples. Main pushes build and scan without publishing. The `v0.9` tag workflow publishes a set of images from the validated current main revision. An operator prepares a GitOps pull request that records the image digests
and target environment before Argo CD sees them. Argo Rollouts runs the frontend update and queries Prometheus
for candidate health. OpenCost reads Kubernetes allocation, and the FinOps CLI keeps those figures separate
from optional AWS billing data.
