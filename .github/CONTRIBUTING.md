# Contributing

## Workflow and Pull Requests

1. Create a feature or fix branch from `main` in this monorepo and keep edits scoped to the relevant component directories (`platform-infra/`, `gitops-config/`, `boutique-app/`, `finops-toolkit/`, `scripts/`, or `.github/`).
2. Use Conventional Commits (for example, `fix(rollouts): handle missing probe series` or `feat(finops): validate prod budget input`) and open a Pull Request against `main`.
3. Include expected behavior, local verification commands executed (see the [quick-start pre-PR checklist](docs/quick-start.md#7-pre-pr-local-validation-checklist)), and any environment variables or fixtures required to reproduce the change.
4. Keep deployment state explicit in `gitops-config/` (via `promote-images.yml` or a reviewed Kustomize PR) so reviewers can inspect exact `@sha256` digests and Kubernetes manifest diffs before Argo CD reconciles them. Never commit credentials, `.tfstate`, `.tfplan`, `*.secret.tfvars`, or unsealed Kubernetes Secrets.

## Branch Protection and Solo-Maintainer GitHub Ruleset Settings

Component ownership boundaries are declared in [CODEOWNERS](CODEOWNERS) (`@workwithcrow12-art`). Because GitHub does not allow a Pull Request author to approve their own PR, enabling strict Code Owner approval on a solo-maintained repository deadlocks merges. Configure the `main` branch Ruleset as follows:

- **Require a pull request before merging:** Enabled (block direct force-pushes and branch deletions on `main`).
- **Require status checks to pass:** Enabled, requiring the root `Release validation` (`ci.yml`) checks to succeed before merging. Every push to `main`—including documentation-only updates—also runs `Release validation` so tagged releases (`release.yml`) always have a verified green `main` commit.
- **Require review from Code Owners:** Leave **disabled** (or grant **Repository admin bypass** to the solo maintainer in the Ruleset bypass list) while team size is `1`. Once a second maintainer joins and is added to [CODEOWNERS](CODEOWNERS), enable mandatory `1+` non-author Code Owner approvals and remove admin bypass for `prod` infrastructure and GitOps overlays.
- **GitHub Environments (`nonprod`, `prod`):** Configure environment-scoped OIDC roles and required reviewers on `prod` before enabling opt-in `.github/workflows/terraform-apply.yml` runs.
