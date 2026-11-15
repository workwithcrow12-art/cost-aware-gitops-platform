locals {
  name = "cost-aware-prod"
  cost_tags = {
    team = "platform", env = "prod", project = "cost-aware-gitops", owner = "platform"
  }
}

module "network" {
  source     = "../../modules/network"
  name       = local.name
  vpc_cidr   = var.vpc_cidr
  az_count   = 3
  nat_per_az = true
}

module "cluster" {
  source                = "../../modules/cluster"
  name                  = local.name
  kubernetes_version    = var.kubernetes_version
  subnet_ids            = module.network.private_subnet_ids
  operator_access_cidrs = var.operator_access_cidrs
  operator_role_arn     = var.operator_role_arn
  capacity_type         = "ON_DEMAND"
  instance_types        = ["m6i.large"]
  node_count            = 3
  cost_tags             = local.cost_tags
  enable_ebs_csi        = true
}
