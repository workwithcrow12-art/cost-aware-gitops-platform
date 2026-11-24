output "role_arns" {
  value = { for name, role in aws_iam_role.github : name => role.arn }
}

output "oidc_provider_arn" {
  value = local.provider_arn
}
