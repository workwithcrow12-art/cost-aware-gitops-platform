locals {
  name = "cost-aware-nonprod"
  cost_tags = {
    team = "platform", env = "nonprod", project = "cost-aware-gitops", owner = "platform"
  }
}

module "network" {
  source     = "../../modules/network"
  name       = local.name
  vpc_cidr   = var.vpc_cidr
  az_count   = 2
  nat_per_az = false
}

module "cluster" {
  source                = "../../modules/cluster"
  name                  = local.name
  kubernetes_version    = var.kubernetes_version
  subnet_ids            = module.network.private_subnet_ids
  operator_access_cidrs = var.operator_access_cidrs
  operator_role_arn     = var.operator_role_arn
  capacity_type         = "SPOT"
  instance_types        = ["m6i.large", "m6a.large", "m5.large"]
  node_count            = 2
  cost_tags             = local.cost_tags
}
