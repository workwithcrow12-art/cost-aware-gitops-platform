# Platform architecture

```mermaid
flowchart LR
    App["boutique-app"] -->|Build and scan| GHCR["GitHub Container Registry"]
    App -->|Propose dev image updates| Config["gitops-config"]
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

The app workflow publishes a set of images from one revision. A GitOps pull request records the image digests
and target environment before Argo CD sees them. Argo Rollouts runs the frontend update and queries Prometheus
for candidate health. OpenCost reads Kubernetes allocation, and the FinOps CLI keeps those figures separate
from optional AWS billing data.
