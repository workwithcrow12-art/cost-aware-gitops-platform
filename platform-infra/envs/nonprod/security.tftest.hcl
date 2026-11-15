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
}

run "nonprod_environment_plan" {
  command = plan

  variables {
    operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
    operator_access_cidrs = ["10.2.1.0/24"]
  }

  assert {
    condition = (
      output.cluster_name == "cost-aware-nonprod" &&
      length(module.network.private_subnet_ids) == 2 &&
      local.cost_tags.env == "nonprod"
    )
    error_message = "The full nonprod plan must wire the nonprod cluster, two private AZ subnets and nonprod cost tags."
  }
}

run "vpc_records_accepted_and_rejected_flows" {
  command = plan

  module {
    source = "../../modules/network"
  }

  variables {
    name       = "cost-aware-test"
    vpc_cidr   = "10.30.0.0/16"
    az_count   = 2
    nat_per_az = false
  }

  assert {
    condition = (
      aws_flow_log.this.traffic_type == "ALL" &&
      aws_flow_log.this.log_destination_type == "cloud-watch-logs" &&
      aws_cloudwatch_log_group.flow_logs.retention_in_days == 14
    )
    error_message = "The VPC must record accepted and rejected flows in CloudWatch Logs."
  }

  assert {
    condition = (
      jsondecode(aws_iam_role.flow_logs.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "123456789012" &&
      jsondecode(aws_iam_role.flow_logs.assume_role_policy).Statement[0].Condition.ArnLike["aws:SourceArn"] == "arn:aws:ec2:ap-southeast-1:123456789012:vpc-flow-log/*"
    )
    error_message = "Flow log delivery must only trust VPC flow logs from this account and region."
  }
}

run "private_cluster_and_explicit_operator" {
  command = plan

  module {
    source = "../../modules/cluster"
  }

  variables {
    name                  = "cost-aware-test"
    kubernetes_version    = "1.35"
    subnet_ids            = ["subnet-00000000000000001", "subnet-00000000000000002"]
    operator_access_cidrs = ["10.2.1.0/24"]
    operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
    capacity_type         = "SPOT"
    instance_types        = ["m6i.large"]
    node_count            = 2
    cost_tags = {
      team = "platform", env = "nonprod", project = "cost-aware-gitops", owner = "platform"
    }
  }

  assert {
    condition     = aws_eks_cluster.this.vpc_config[0].endpoint_private_access && !aws_eks_cluster.this.vpc_config[0].endpoint_public_access
    error_message = "The EKS Kubernetes API must only be available through the private endpoint."
  }

  assert {
    condition     = !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions
    error_message = "EKS must not grant implicit cluster admin access to the creator."
  }

  assert {
    condition = (
      aws_eks_access_policy_association.operator.principal_arn == var.operator_role_arn &&
      aws_vpc_security_group_ingress_rule.operator["10.2.1.0/24"].from_port == 443 &&
      aws_vpc_security_group_ingress_rule.operator["10.2.1.0/24"].to_port == 443
    )
    error_message = "The explicit operator must have access and the routed CIDR must be restricted to the Kubernetes API port."
  }

  assert {
    condition = (
      jsondecode(aws_eks_addon.vpc_cni.configuration_values).enableNetworkPolicy == "true" &&
      !contains(keys(aws_iam_role_policy_attachment.nodes), "AmazonEKS_CNI_Policy")
    )
    error_message = "The managed VPC CNI must enforce network policies and node IAM roles must not have the CNI policy."
  }

  assert {
    condition = (
      toset([for spec in aws_launch_template.system.tag_specifications : spec.resource_type]) == toset(["instance", "volume"]) &&
      alltrue([for spec in aws_launch_template.system.tag_specifications : spec.tags == var.cost_tags]) &&
      length(aws_eks_node_group.system.launch_template) == 1
    )
    error_message = "The system node group must launch EC2 instances and EBS volumes with all environment cost tags."
  }

  assert {
    condition = (
      length(aws_launch_template.system.metadata_options) == 1 &&
      alltrue([for options in aws_launch_template.system.metadata_options :
        options.http_tokens == "required" && options.http_put_response_hop_limit == 1
      ])
    )
    error_message = "The custom launch template must require IMDSv2 and retain hop limit 1 so ordinary pods cannot retrieve node credentials."
  }
}
