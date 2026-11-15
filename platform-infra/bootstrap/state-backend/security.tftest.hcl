mock_provider "aws" {
  mock_resource "aws_s3_bucket" {
    override_during = plan
    defaults        = { arn = "arn:aws:s3:::cost-aware-terraform-test" }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
}

run "optional_aws_integrations" {
  command = plan

  variables {
    athena_results_s3 = "s3://cost-aware-results/finops/"
    github_actions = {
      repository          = "example/platform-infra"
      repository_owner_id = "101"
      repository_id       = "202"
      oidc_provider_arn   = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      plan_policy_arn     = "arn:aws:iam::123456789012:policy/TerraformDriftRead"
      apply_policy_arns = {
        nonprod = "arn:aws:iam::123456789012:policy/TerraformNonprodApply"
        prod    = "arn:aws:iam::123456789012:policy/TerraformProdApply"
      }
    }
  }

  assert {
    condition = (
      local.github_subject == "repo:example@101/platform-infra@202" &&
      toset(keys(output.github_role_arns)) == toset(["plan", "apply-nonprod", "apply-prod"]) &&
      output.athena_workgroup == "cost-aware-finops"
    )
    error_message = "Optional deployment roles must use immutable repository identity and the Athena workgroup must be configured."
  }
}

variables {
  state_bucket_name  = "cost-aware-terraform-test"
  budget_email       = "budget@example.com"
  monthly_budget_usd = 250
}

run "managed_reporting_from_cur_prefix" {
  command = plan
  variables {
    athena_cur_catalog = {
      database_name = "finops"
      table_name    = "cur"
      data_s3       = "s3://billing-data/cur/parquet/"
    }
  }
  assert {
    condition = (
      output.athena_workgroup == "cost-aware-finops" &&
      output.athena_reporter_environment.ATHENA_DATABASE == "finops" &&
      output.athena_reporter_environment.ATHENA_TABLE == "cur"
    )
    error_message = "A CUR prefix must enable the catalog and workgroup without an existing results bucket."
  }
}

run "deny_plaintext_state_requests" {
  command = plan

  assert {
    condition = anytrue([
      for statement in jsondecode(aws_s3_bucket_policy.state_tls.policy).Statement :
      statement.Effect == "Deny" && statement.Principal == "*" && statement.Action == "s3:*" &&
      toset(statement.Resource) == toset(["arn:aws:s3:::cost-aware-terraform-test", "arn:aws:s3:::cost-aware-terraform-test/*"]) &&
      statement.Condition.Bool["aws:SecureTransport"] == "false"
    ])
    error_message = "State bucket and object requests must deny insecure transport."
  }
}
