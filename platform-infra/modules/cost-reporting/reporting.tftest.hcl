mock_provider "aws" {
  mock_resource "aws_s3_bucket" {
    override_during = plan
    defaults = {
      id  = "finops-results-test"
      arn = "arn:aws:s3:::finops-results-test"
    }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { region = "ap-southeast-1" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
}

variables {
  name = "finops-test"
}

run "managed_catalog_and_reporter" {
  command = plan

  variables {
    cur_catalog = {
      database_name = "finops"
      table_name    = "cur"
      data_s3       = "s3://billing-data/cur/parquet/"
    }
    reporter = {
      oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
      oidc_issuer_url   = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
    }
  }

  assert {
    condition = (
      length(aws_s3_bucket.results) == 1 &&
      aws_s3_bucket_public_access_block.results[0].block_public_policy &&
      aws_s3_bucket_server_side_encryption_configuration.results[0].rule != null &&
      aws_glue_catalog_table.cur[0].storage_descriptor[0].location == "s3://billing-data/cur/parquet/" &&
      output.reporter_environment.ATHENA_TABLE == "cur" &&
      output.reporter_environment.ATHENA_DATABASE == "finops"
    )
    error_message = "Reporting must provision a private encrypted results bucket, CUR catalog and runtime configuration."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role.reporter[0].assume_role_policy).Statement[0].Condition.StringEquals["oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE:sub"] == "system:serviceaccount:finops:finops-reporter" &&
      jsondecode(aws_iam_role_policy.reporter[0].policy).Statement[0].Resource == "arn:aws:athena:ap-southeast-1:123456789012:workgroup/finops-test" &&
      jsondecode(aws_iam_role_policy.reporter[0].policy).Statement[2].Resource == "arn:aws:s3:::billing-data/cur/parquet/*"
    )
    error_message = "The reporter role must trust only its ServiceAccount and scope queries and CUR reads."
  }
}

run "existing_results_workgroup_only" {
  command = plan

  variables {
    results_s3 = "s3://existing-results/finops"
  }

  assert {
    condition = (
      length(aws_s3_bucket.results) == 0 &&
      length(aws_glue_catalog_table.cur) == 0 &&
      length(aws_iam_role.reporter) == 0 &&
      output.results_s3 == "s3://existing-results/finops/" &&
      aws_athena_workgroup.reporting.configuration[0].bytes_scanned_cutoff_per_query == 5368709120
    )
    error_message = "Existing callers must retain the workgroup-only behavior and scan cap."
  }
}

run "reject_reporter_without_catalog" {
  command = plan

  variables {
    results_s3 = "s3://existing-results/finops/"
    reporter = {
      oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/issuer.example"
      oidc_issuer_url   = "https://issuer.example"
    }
  }

  expect_failures = [var.reporter]
}
