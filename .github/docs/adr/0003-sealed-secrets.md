# ADR-0003: Sealed Secrets for secret management

- **Status:** Accepted for optional integration credentials

## Context

The baseline deploy uses public images and can run a local report without credentials.
Optional notification and API integrations need Kubernetes secrets.

## Options considered

1. Create Kubernetes Secrets out of band for the lab.
2. Use Sealed Secrets to store encrypted, cluster-bound manifests with the deployment configuration.

## Decision

Install the Sealed Secrets controller with the platform add-ons. Use sealed manifests for optional integration
credentials that need to travel through Git.

## Consequences

A fresh cluster requires credential provisioning or restoration of the controller's private key.
When using a new key, reseal each credential for the target cluster.
