# ADR-0004: Canary releases for the frontend only

- **Status:** Accepted for the portfolio lab

## Context

The frontend is the user-facing entry point and provides a direct HTTP signal for the demo.

## Options considered

1. Roll out every service progressively with separate service-specific signals.
2. Canary the frontend and use standard Deployment updates for the backend services.

## Decision

Canary the frontend through Argo Rollouts and use Prometheus to check a candidate-only Service.

## Consequences

The lab can exercise an abort with one failing probe. Rollouts adjusts replica proportions and the
probe reports synthetic HTTP health. Evaluate a traffic router and user-traffic metrics for production use.
