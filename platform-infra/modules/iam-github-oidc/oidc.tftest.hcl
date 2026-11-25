mock_provider "aws" {
  mock_resource "aws_iam_openid_connect_provider" {
    override_during = plan
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    }
  }
}

variables {
  name_prefix = "cost-aware-ci"
  roles = {
    plan = {
      subjects   = ["repo:example@101/platform-infra@202:ref:refs/heads/main"]
      policy_arn = "arn:aws:iam::123456789012:policy/TerraformPlan"
    }
  }
}

run "creates_provider_and_enforces_string_equals" {
  command = plan

  assert {
    condition = (
      length(aws_iam_openid_connect_provider.github) == 1 &&
      aws_iam_openid_connect_provider.github[0].url == "https://token.actions.githubusercontent.com" &&
      jsondecode(aws_iam_role.github["plan"].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com" &&
      contains(jsondecode(aws_iam_role.github["plan"].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"], "repo:example@101/platform-infra@202:ref:refs/heads/main")
    )
    error_message = "GitHub OIDC roles must enforce exact StringEquals conditions on both aud and sub."
  }
}

run "reuses_existing_oidc_provider" {
  command = plan

  variables {
    provider_arn             = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
    permissions_boundary_arn = "arn:aws:iam::123456789012:policy/Boundary"
  }

  assert {
    condition = (
      length(aws_iam_openid_connect_provider.github) == 0 &&
      aws_iam_role.github["plan"].permissions_boundary == "arn:aws:iam::123456789012:policy/Boundary"
    )
    error_message = "Supplying provider_arn must reuse the existing account OIDC provider."
  }
}

run "rejects_wildcard_or_unscoped_subjects" {
  command = plan

  variables {
    roles = {
      wildcard = {
        subjects   = ["repo:example/*"]
        policy_arn = "arn:aws:iam::123456789012:policy/TerraformPlan"
      }
    }
  }

  expect_failures = [var.roles]
}
