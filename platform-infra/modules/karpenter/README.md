# Karpenter Module (Opt-in)

Provisions AWS IAM and Spot/health interruption infrastructure for Karpenter v1:

- **Controller IRSA role** bound via `StringEquals` to `system:serviceaccount:<namespace>:<service_account>`, with `iam:PassRole` restricted to the dedicated Karpenter node role.
- **Node IAM role & EKS Access Entry (`EC2_LINUX`)** with `AmazonEKSWorkerNodePolicy`, `AmazonEC2ContainerRegistryPullOnly`, and `AmazonSSMManagedInstanceCore`.
- **SSE-encrypted SQS interruption queue** and four EventBridge rules (Spot interruption warnings, rebalance recommendations, instance state changes, and AWS Health scheduled events).

`envs/nonprod` and `envs/prod` keep `enable_karpenter = false` by default so baseline cost comparisons remain deterministic against fixed managed node groups. Enable `enable_karpenter = true` when evaluating dynamic node consolidation.
