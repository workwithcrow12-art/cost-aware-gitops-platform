mock_provider "aws" {
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_eks_addon_version" {
    defaults = { version = "v1.21.0-eksbuild.1" }
  }
  mock_data "aws_availability_zones" {
    defaults = { names = ["ap-southeast-1a", "ap-southeast-1b", "ap-southeast-1c"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { region = "ap-southeast-1" }
  }
  mock_resource "aws_kms_key" {
    override_during = plan
    defaults = {
      arn = "arn:aws:kms:ap-southeast-1:123456789012:key/prod-test-key"
    }
  }
  mock_resource "aws_s3_bucket" {
    override_during = plan
    defaults = {
      id  = "finops-results-prod"
      arn = "arn:aws:s3:::finops-results-prod"
    }
  }
  mock_resource "aws_eks_cluster" {
    override_during = plan
    defaults = {
      identity = [{ oidc = [{ issuer = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/PROD" }] }]
    }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    override_during = plan
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/PROD"
      url = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/PROD"
    }
  }
}

variables {
  operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
  operator_access_cidrs = ["10.2.1.0/24"]
  budget = {
    monthly_limit_usd = 500
    email             = "finops@example.com"
  }
}

run "prod_environment_plan" {
  command = plan

  assert {
    condition = (
      output.cluster_name == "cost-aware-prod" &&
      output.budget_name == "cost-aware-prod-monthly" &&
      length(module.network.private_subnet_ids) == 3 &&
      local.cost_tags.env == "prod" &&
      var.nat_per_az &&
      var.enable_ebs_csi &&
      module.cluster.operator_policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy" &&
      module.cluster.break_glass_policy_arn == null
    )
    error_message = "The full prod plan must wire the prod cluster, mandatory budget, three private AZ subnets, per-AZ NAT, EBS CSI, default read-only operator access, and prod cost tags."
  }
}

run "prod_wires_optional_budget_reporting_oidc_and_endpoints" {
  command = plan

  variables {
    operator_access_policy     = "AmazonEKSEditPolicy"
    break_glass_role_arn       = "arn:aws:iam::123456789012:role/ClusterBreakGlass"
    enable_interface_endpoints = true
    enable_karpenter           = true
    cost_reporting = {
      enable_reporter = true
      cur_catalog = {
        database_name = "finops_prod"
        table_name    = "cur"
        data_s3       = "s3://billing-data/cur/parquet/"
      }
    }
    github_oidc = {
      provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      roles = {
        apply = {
          subjects   = ["repo:example/platform:environment:prod"]
          policy_arn = "arn:aws:iam::123456789012:policy/ProdApply"
        }
      }
    }
  }

  assert {
    condition = (
      output.budget_name == "cost-aware-prod-monthly" &&
      output.athena_workgroup == "cost-aware-prod-finops" &&
      length(module.karpenter) == 1 &&
      length(module.github_oidc) == 1 &&
      module.cluster.operator_policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy" &&
      module.cluster.break_glass_principal_arn == "arn:aws:iam::123456789012:role/ClusterBreakGlass" &&
      module.cluster.break_glass_policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
    )
    error_message = "Prod must cleanly instantiate mandatory budget, cost-reporting, OIDC, interface endpoints, Karpenter, and break-glass cluster admin."
  }
}

run "prod_rejects_null_or_zero_budget" {
  command = plan

  variables {
    budget = {
      monthly_limit_usd = 0
      email             = "finops@example.com"
    }
  }

  expect_failures = [var.budget]
}

run "prod_rejects_world_operator_cidr" {
  command = plan

  variables {
    operator_access_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [var.operator_access_cidrs]
}

run "prod_rejects_admin_routine_operator_policy" {
  command = plan

  variables {
    operator_access_policy = "AmazonEKSClusterAdminPolicy"
  }

  expect_failures = [var.operator_access_policy]
}

run "prod_rejects_duplicate_break_glass_role" {
  command = plan

  variables {
    break_glass_role_arn = "arn:aws:iam::123456789012:role/ClusterOperator"
  }

  expect_failures = [var.break_glass_role_arn]
}
