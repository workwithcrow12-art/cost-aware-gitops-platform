# ADR-0002: Kustomize for the application, Helm for platform add-ons

- **Status:** Accepted for the portfolio lab

## Context

The lab owns its Online Boutique deployment files and consumes charts from upstream add-on maintainers.

## Options considered

1. Use Helm for both the app and add-ons, with templates for environment differences.
2. Use Kustomize overlays for the app and upstream Helm charts for add-ons.

## Decision

Use Kustomize for the shared app base and per-environment patches. Pin Helm chart versions for add-ons.

## Consequences

A promotion edits a small image list in one overlay. Validate both the Kustomize output and the chart
configuration when changing an add-on.
