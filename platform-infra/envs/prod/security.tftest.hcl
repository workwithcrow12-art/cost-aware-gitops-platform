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
      local.cost_tags.env == "prod"
    )
    error_message = "The full prod plan must wire the prod cluster, three private AZ subnets and prod cost tags."
  }
}
