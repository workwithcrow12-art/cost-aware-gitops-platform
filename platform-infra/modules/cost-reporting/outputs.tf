output "workgroup_name" {
  value = aws_athena_workgroup.reporting.name
}

output "results_s3" {
  value = local.results_s3
}

output "reporter_role_arn" {
  value = var.reporter == null ? null : aws_iam_role.reporter[0].arn
}

output "reporter_environment" {
  value = var.cur_catalog == null ? {} : {
    AWS_REGION       = data.aws_region.current.region
    ATHENA_DATABASE  = var.cur_catalog.database_name
    ATHENA_TABLE     = var.cur_catalog.table_name
    ATHENA_WORKGROUP = aws_athena_workgroup.reporting.name
    ATHENA_OUTPUT_S3 = local.results_s3
  }
}
