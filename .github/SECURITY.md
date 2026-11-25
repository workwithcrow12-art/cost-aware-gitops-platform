# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `1.0.x` / `main` | Yes |
| `< 1.0` | No |

## Scope

Security reports cover this monorepo's platform infrastructure (`platform-infra/`), GitOps manifests and admission policies (`gitops-config/`), FinOps CLI (`finops-toolkit/`), CI/CD workflows (`.github/workflows/`), and build/deployment wrappers around `boutique-app/`. Upstream Google Online Boutique vulnerabilities may also be reported directly to [GoogleCloudPlatform/microservices-demo](https://github.com/GoogleCloudPlatform/microservices-demo/security).

## Reporting a Vulnerability

1. **Preferred channel:** Open a private report via **Security → Report a vulnerability** on [workwithcrow12-art/cost-aware-gitops-platform](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/security/advisories/new).
2. **Fallback contact:** If private vulnerability reporting is unavailable, contact `@workwithcrow12-art` through the email or profile links listed on [github.com/workwithcrow12-art](https://github.com/workwithcrow12-art) before filing any public issue. Never post exploit details, live tokens, cloud account IDs, or private logs in public issues or pull requests.

Please include the commit SHA, affected component path, preconditions, minimal reproduction steps, and expected impact. Maintainers aim to acknowledge reports within 7 days.
