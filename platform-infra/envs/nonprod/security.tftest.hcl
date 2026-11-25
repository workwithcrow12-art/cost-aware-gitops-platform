mock_provider "aws" {
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_eks_addon_version" {
    defaults = { version = "v1.21.0-eksbuild.1" }
  }
  mock_data "aws_availability_zones" {
    defaults = { names = ["ap-southeast-1a", "ap-southeast-1b"] }
  }
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { region = "ap-southeast-1" }
  }
  mock_resource "aws_kms_key" {
    override_during = plan
    defaults        = { arn = "arn:aws:kms:ap-southeast-1:123456789012:key/nonprod-test-key" }
  }
  mock_resource "aws_s3_bucket" {
    override_during = plan
    defaults        = { id = "finops-results-nonprod", arn = "arn:aws:s3:::finops-results-nonprod" }
  }
  mock_resource "aws_eks_cluster" {
    override_during = plan
    defaults = {
      identity = [{ oidc = [{ issuer = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/NONPROD" }] }]
    }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    override_during = plan
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/NONPROD"
      url = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/NONPROD"
    }
  }
}

run "nonprod_environment_plan_with_ebs_csi_parity" {
  command = plan

  variables {
    operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_cidrs = ["10.2.1.0/24"]
  }

  assert {
    condition = (
      output.cluster_name == "cost-aware-nonprod" &&
      length(module.network.private_subnet_ids) == 2 &&
      local.cost_tags.env == "nonprod" &&
      var.enable_ebs_csi &&
      module.cluster.operator_policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy" &&
      module.cluster.break_glass_policy_arn == null
    )
    error_message = "Nonprod plan must wire the nonprod cluster, two private AZ subnets, EBS CSI parity, default read-only operator access, and nonprod cost tags."
  }
}

run "nonprod_wires_optional_finops_oidc_karpenter_and_break_glass" {
  command = plan

  variables {
    operator_role_arn      = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_policy = "AmazonEKSEditPolicy"
    break_glass_role_arn   = "arn:aws:iam::123456789012:role/ClusterBreakGlass"
    operator_access_cidrs  = ["10.2.1.0/24"]
    enable_karpenter       = true
    budget                 = { monthly_limit_usd = 150, email = "finops@example.com" }
    cost_reporting = {
      enable_reporter = true
      cur_catalog     = { database_name = "finops_nonprod", table_name = "cur", data_s3 = "s3://billing-data/cur/parquet/" }
    }
    github_oidc = {
      provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
      roles = {
        apply = {
          subjects   = ["repo:example/platform:environment:nonprod"]
          policy_arn = "arn:aws:iam::123456789012:policy/NonprodApply"
        }
      }
    }
  }

  assert {
    condition = (
      output.budget_name == "cost-aware-nonprod-monthly" &&
      output.athena_workgroup == "cost-aware-nonprod-finops" &&
      length(module.karpenter) == 1 &&
      length(module.github_oidc) == 1 &&
      module.cluster.operator_policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy" &&
      module.cluster.break_glass_principal_arn == "arn:aws:iam::123456789012:role/ClusterBreakGlass" &&
      module.cluster.break_glass_policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
    )
    error_message = "Optional environment modules and break-glass cluster admin must wire cleanly when configured."
  }
}

run "nonprod_rejects_world_operator_cidr" {
  command = plan

  variables {
    operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [var.operator_access_cidrs]
}

run "nonprod_rejects_admin_routine_operator_policy" {
  command = plan

  variables {
    operator_role_arn      = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_policy = "AmazonEKSClusterAdminPolicy"
    operator_access_cidrs  = ["10.2.1.0/24"]
  }

  expect_failures = [var.operator_access_policy]
}

run "nonprod_rejects_duplicate_break_glass_role" {
  command = plan

  variables {
    operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
    break_glass_role_arn  = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_cidrs = ["10.2.1.0/24"]
  }

  expect_failures = [var.break_glass_role_arn]
}
