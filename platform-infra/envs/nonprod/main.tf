locals {
  name = "cost-aware-nonprod"
  cost_tags = {
    team = "platform", env = "nonprod", project = "cost-aware-gitops", owner = "platform"
  }
}

module "network" {
  source                     = "../../modules/network"
  name                       = local.name
  vpc_cidr                   = var.vpc_cidr
  az_count                   = 2
  nat_per_az                 = false
  enable_interface_endpoints = var.enable_interface_endpoints
}

module "cluster" {
  source                 = "../../modules/cluster"
  name                   = local.name
  kubernetes_version     = var.kubernetes_version
  subnet_ids             = module.network.private_subnet_ids
  operator_access_cidrs  = var.operator_access_cidrs
  operator_role_arn      = var.operator_role_arn
  operator_access_policy = var.operator_access_policy
  break_glass_role_arn   = var.break_glass_role_arn
  capacity_type          = "SPOT"
  instance_types         = ["m6i.large", "m6a.large", "m5.large"]
  node_count             = 2
  cost_tags              = local.cost_tags
  enable_ebs_csi         = var.enable_ebs_csi
}

module "budget" {
  count  = var.budget == null ? 0 : 1
  source = "../../modules/budgets"

  name                      = "${local.name}-monthly"
  monthly_limit_usd         = var.budget.monthly_limit_usd
  email                     = var.budget.email
  additional_emails         = var.budget.additional_emails
  subscriber_sns_topic_arns = var.budget.subscriber_sns_topic_arns
  cost_filters = {
    TagKeyValue = [format("user:env$%s", local.cost_tags.env)]
  }
}

module "cost_reporting" {
  count  = var.cost_reporting == null ? 0 : 1
  source = "../../modules/cost-reporting"

  name                 = "${local.name}-finops"
  results_s3           = var.cost_reporting.results_s3
  results_bucket_owner = var.cost_reporting.results_bucket_owner
  cur_catalog          = var.cost_reporting.cur_catalog
  reporter = var.cost_reporting.enable_reporter ? {
    oidc_provider_arn = module.cluster.oidc_provider_arn
    oidc_issuer_url   = module.cluster.oidc_issuer_url
  } : null
}

module "github_oidc" {
  count  = var.github_oidc == null ? 0 : 1
  source = "../../modules/iam-github-oidc"

  name_prefix              = "${local.name}-gha"
  provider_arn             = var.github_oidc.provider_arn
  permissions_boundary_arn = var.github_oidc.permissions_boundary_arn
  roles                    = var.github_oidc.roles
}

module "karpenter" {
  count  = var.enable_karpenter ? 1 : 0
  source = "../../modules/karpenter"

  cluster_name      = module.cluster.name
  oidc_provider_arn = module.cluster.oidc_provider_arn
  oidc_issuer_url   = module.cluster.oidc_issuer_url
}
