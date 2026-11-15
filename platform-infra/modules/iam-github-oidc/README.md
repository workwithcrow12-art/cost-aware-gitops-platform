# GitHub OIDC roles

Creates IAM roles for exact GitHub token subjects with `sts.amazonaws.com` as audience. Supply `name_prefix` and a `roles` map with a `subjects` set and an existing IAM `policy_arn` per role. Supply `provider_arn` to reuse an existing GitHub OIDC provider or leave it unset to create one. Set `permissions_boundary_arn` to cap the effective permissions of the roles. The module outputs `role_arns`.

## Configure GitHub OIDC

The [shared bootstrap](../../bootstrap/state-backend/main.tf) uses immutable repository identity and the exact workflow file on `main`. Configure the repository-level subject template to include `repo`, `context` and `workflow_ref` in that order. If the repository already has federated workloads, inventory their trust policies and coordinate the template change with their owners before changing it.

Run these commands as a GitHub repository administrator after setting `repository` to the repository's actual owner and name.

```bash
repository='YOUR-OWNER/platform-infra'
gh api "repos/$repository" --jq '{repository: .full_name, repository_owner_id: .owner.id, repository_id: .id}'
gh api --method PUT "repos/$repository/actions/oidc/customization/sub" \
  -H 'X-GitHub-Api-Version: 2026-03-10' \
  -F use_default=false -F use_immutable_subject=true \
  -f 'include_claim_keys[]=repo' -f 'include_claim_keys[]=context' -f 'include_claim_keys[]=workflow_ref'
```

Set `github_actions.repository`, `github_actions.repository_owner_id` and `github_actions.repository_id` from the API response. Use that response's exact name casing. Provide `plan_policy_arn` for the drift reader and `apply_policy_arns` with a policy ARN for each of `nonprod` and `prod`. Reuse any existing AWS OIDC provider with `oidc_provider_arn`, and supply `permissions_boundary_arn` when the account uses a boundary for CI roles. An apply subject looks like `repo:owner@101/platform-infra@202:environment:nonprod:workflow_ref:owner/platform-infra/.github/workflows/terraform-apply.yml@refs/heads/main`. Keep the repository rules for `main` and the GitHub deployment environments enabled.

## Scope the AWS permission policies

The plan role is used by drift detection and the plan job in `terraform-apply.yml`, both on `main`. It needs resource reads and S3 ListBucket/GetObject for the environment state keys, plus GetObject/PutObject/DeleteObject for their `.tflock` keys so reviewed plans can lock state. It must not write the state objects or infrastructure. Each deployment role needs writes only for its environment's state and permission to get, put and delete that environment's lockfile. Scope infrastructure permissions to the configured region and environment. Restrict `iam:PassRole` to the cluster, node, VPC CNI, EBS CSI and flow-log roles and the intended AWS services. Constrain IAM writes so an apply role cannot modify its own trust or permission boundary, the plan and other environment roles, or the GitHub OIDC provider. Create and review these account-specific policies before enabling the module.
