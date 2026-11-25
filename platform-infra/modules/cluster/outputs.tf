output "name" {
  value = aws_eks_cluster.this.name
}

output "arn" {
  value = aws_eks_cluster.this.arn
}

output "endpoint" {
  value = aws_eks_cluster.this.endpoint
}

output "oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.cluster.arn
}

output "oidc_issuer_url" {
  value = aws_iam_openid_connect_provider.cluster.url
}

output "kms_key_arn" {
  value = aws_kms_key.cluster.arn
}

output "operator_policy_arn" {
  value = aws_eks_access_policy_association.operator.policy_arn
}

output "break_glass_principal_arn" {
  value = var.break_glass_role_arn == null ? null : aws_eks_access_entry.break_glass[0].principal_arn
}

output "break_glass_policy_arn" {
  value = var.break_glass_role_arn == null ? null : aws_eks_access_policy_association.break_glass[0].policy_arn
}
