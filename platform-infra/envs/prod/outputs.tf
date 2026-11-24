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

output "budget_name" {
  value = var.budget == null ? null : module.budget[0].budget_name
}

output "athena_workgroup" {
  value = var.cost_reporting == null ? null : module.cost_reporting[0].workgroup_name
}

output "karpenter_controller_role_arn" {
  value = var.enable_karpenter ? module.karpenter[0].controller_role_arn : null
}
