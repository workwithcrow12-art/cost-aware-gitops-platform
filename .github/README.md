# .github

Repository workflows, governance files, architecture records, and operational documentation for **Cost-aware GitOps Platform**.

For a technical interview or code walkthrough, start with the [5-minute offline demo](docs/demo.md) and [local readiness verification record](docs/evidence/portfolio-readiness-2026-11-16.md). Before provisioning cloud infrastructure, review the [AWS lab prerequisites and evidence runbook](docs/runbooks/aws-lab-evidence.md).

Follow the [quick-start guide](docs/quick-start.md) and the [review comparison and remediation record](docs/comparison-remediation.md) for end-to-end component workflows.

| Path | Purpose |
| --- | --- |
| `workflows/` | Active root monorepo CI validation, offline Terraform plan/Infracost gates, Kyverno checks, GHCR release, `promote-images.yml` GitOps PR automation, and opt-in OIDC apply/drift/Custodian workflows |
| `docs/architecture/` | Platform architecture diagram, access model, and deployment boundaries |
| `docs/adr/` | Architecture Decision Records |
| `docs/runbooks/` | Step-by-step operational procedures (EKS rebuild, lab evidence, rollback, budget alerts) |
| `docs/postmortems/` | Canary auto-rollback fault-injection drill and incident template |
| `docs/case-study.md` | Local verification commands and live cloud measurement protocol |
| `docs/portfolio.md` | Project summary, CV bullets, interview walkthrough, and engineering tradeoffs |
| `docs/evidence/` | Generated, explicitly synthetic FinOps demo reports and verification logs |
| `CONTRIBUTING.md`, `SECURITY.md`, `CODEOWNERS` | Contribution workflow, solo-maintainer GitHub Ruleset guidance, and security reporting |
