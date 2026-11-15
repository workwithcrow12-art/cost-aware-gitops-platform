data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  results_s3 = var.results_s3 == null ? "s3://${aws_s3_bucket.results[0].id}/finops/" : "${trimsuffix(var.results_s3, "/")}/"
}

resource "aws_athena_workgroup" "reporting" {
  name        = var.name
  description = "Queries AWS Cost and Usage Report data."

  configuration {
    bytes_scanned_cutoff_per_query     = 5 * 1024 * 1024 * 1024
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location       = local.results_s3
      expected_bucket_owner = coalesce(var.results_bucket_owner, data.aws_caller_identity.current.account_id)

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}
