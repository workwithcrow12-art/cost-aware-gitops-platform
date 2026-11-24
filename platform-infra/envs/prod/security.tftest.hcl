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

run "prod_environment_plan" {
  command = plan

  variables {
    operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_cidrs = ["10.2.1.0/24"]
  }

  assert {
    condition = (
      output.cluster_name == "cost-aware-prod" &&
      length(module.network.private_subnet_ids) == 3 &&
      local.cost_tags.env == "prod" &&
      var.enable_ebs_csi
    )
    error_message = "The full prod plan must wire the prod cluster, three private AZ subnets, EBS CSI and prod cost tags."
  }
}

run "prod_wires_optional_budget_reporting_oidc_and_endpoints" {
  command = plan

  variables {
    operator_role_arn          = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_cidrs      = ["10.2.1.0/24"]
    enable_interface_endpoints = true
    enable_karpenter           = true
    budget = {
      monthly_limit_usd = 500
      email             = "finops@example.com"
    }
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
      length(module.github_oidc) == 1
    )
    error_message = "Prod must cleanly instantiate optional budget, cost-reporting, OIDC, interface endpoints and Karpenter modules."
  }
}

run "prod_rejects_world_operator_cidr" {
  command = plan

  variables {
    operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [module.cluster.var.operator_access_cidrs]
}
