output "cluster_name" {
  value = module.cluster.name
}

output "cluster_arn" {
  value = module.cluster.arn
}

output "cluster_endpoint" {
  value = module.cluster.endpoint
}

output "cluster_oidc_provider_arn" {
  value = module.cluster.oidc_provider_arn
}

output "aws_region" {
  value = var.aws_region
}
