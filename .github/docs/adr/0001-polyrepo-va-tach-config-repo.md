# ADR-0001: Polyrepo and a separate GitOps config repository

- **Status:** Superseded for v0.9 by the owner-selected monorepo

## Context

Application builds, cluster infrastructure and deployment approvals change at different rates.
The lab needs a history of what each environment intended to run.

## Options considered

1. A monorepo keeps cross-cutting changes atomic and simplifies checkout.
2. Separate repositories let teams review application and deployment changes independently.

## Decision

Use separate repositories. Application CI opens a PR in `gitops-config` after publishing images.
Argo CD watches the config repository for desired state.

## Consequences

Deployment intent is visible in the config history. Cross-repo changes require coordinated PRs
and a GitHub credential scoped to the config repository.

## v0.9 publication decision

The owner selected `workwithcrow12-art/cost-aware-gitops-platform` as the single publication target. Component directories preserve the original boundaries. Active workflows are at repository root; Argo CD source paths include `gitops-config/`. Deployment changes remain reviewable GitOps pull requests in this repository. The standalone cross-repository promotion workflows are examples, not active automation.
