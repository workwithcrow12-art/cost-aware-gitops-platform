# ADR-0005: One cost-label convention across Terraform, Kubernetes and OpenCost

- **Status:** Accepted for the portfolio lab

## Context

Cost reporting needs a consistent way to group AWS resources and Kubernetes workloads.

## Options considered

1. Infer ownership from resource names and namespaces.
2. Apply explicit tags and labels, then check them at the infrastructure and workload boundaries.

## Decision

Use `team` and `env` for reporting dimensions. Terraform also uses `project` and `owner` for
AWS resources that support tags.

## Consequences

Reports can group explicitly labelled resources. AWS billing tags must be activated, and historical
or shared charges may have no team assignment.
