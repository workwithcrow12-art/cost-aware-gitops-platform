output "state_bucket_name" {
  value = aws_s3_bucket.state.bucket
}

output "state_bucket_region" {
  value = var.aws_region
}

output "budget_name" {
  value = module.budget.budget_name
}

output "athena_workgroup" {
  value = one(module.cost_reporting[*].workgroup_name)
}

output "athena_reporter_environment" {
  value = try(module.cost_reporting[0].reporter_environment, {})
}

output "athena_reporter_role_arn" {
  value = try(module.cost_reporting[0].reporter_role_arn, null)
}

output "athena_results_s3" {
  value = one(module.cost_reporting[*].results_s3)
}

output "github_role_arns" {
  value = var.github_actions == null ? {} : module.github_actions[0].role_arns
}
