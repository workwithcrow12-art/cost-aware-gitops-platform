mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { region = "ap-southeast-1" }
  }
  mock_data "aws_eks_addon_version" {
    defaults = { version = "v1.21.0-eksbuild.1" }
  }
  mock_resource "aws_kms_key" {
    override_during = plan
    defaults        = { arn = "arn:aws:kms:ap-southeast-1:123456789012:key/test-cluster-key" }
  }
  mock_resource "aws_eks_cluster" {
    override_during = plan
    defaults = {
      identity = [{ oidc = [{ issuer = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/TEST" }] }]
    }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    override_during = plan
    defaults = {
      arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/TEST"
      url = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/TEST"
    }
  }
}

variables {
  name                  = "storage-test"
  kubernetes_version    = "1.35"
  subnet_ids            = ["subnet-0123456789abcdef0", "subnet-0123456789abcdef1"]
  operator_access_cidrs = ["10.2.1.0/24"]
  operator_role_arn     = "arn:aws:iam::123456789012:role/ClusterOperator"
  capacity_type         = "ON_DEMAND"
  instance_types        = ["m6i.large"]
  node_count            = 3
  cost_tags             = { team = "platform", env = "prod", project = "test", owner = "platform" }
}

run "private_cluster_imdsv2_and_storage_disabled_by_default" {
  command = plan
  assert {
    condition = (
      length(aws_eks_addon.ebs_csi) == 0 &&
      length(aws_iam_role.ebs_csi) == 0 &&
      length(aws_eks_access_entry.break_glass) == 0 &&
      length(aws_eks_access_policy_association.break_glass) == 0 &&
      aws_eks_cluster.this.vpc_config[0].endpoint_private_access &&
      !aws_eks_cluster.this.vpc_config[0].endpoint_public_access &&
      !aws_eks_cluster.this.access_config[0].bootstrap_cluster_creator_admin_permissions &&
      aws_eks_access_policy_association.operator.principal_arn == var.operator_role_arn &&
      aws_eks_access_policy_association.operator.policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSViewPolicy" &&
      aws_vpc_security_group_ingress_rule.operator["10.2.1.0/24"].to_port == 443 &&
      jsondecode(aws_eks_addon.vpc_cni.configuration_values).enableNetworkPolicy == "true" &&
      !contains(keys(aws_iam_role_policy_attachment.nodes), "AmazonEKS_CNI_Policy") &&
      aws_launch_template.system.metadata_options[0].http_tokens == "required" &&
      aws_launch_template.system.metadata_options[0].http_put_response_hop_limit == 1
    )
    error_message = "Cluster must enforce private API, default AmazonEKSViewPolicy operator RBAC, no break-glass admin by default, VPC CNI policy, IMDSv2 hop-limit 1, and disabled CSI by default."
  }
}

run "break_glass_role_grants_cluster_admin_and_edit_operator_policy" {
  command = plan
  variables {
    operator_access_policy = "AmazonEKSEditPolicy"
    break_glass_role_arn   = "arn:aws:iam::123456789012:role/ClusterBreakGlass"
  }
  assert {
    condition = (
      aws_eks_access_policy_association.operator.policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy" &&
      length(aws_eks_access_entry.break_glass) == 1 &&
      aws_eks_access_entry.break_glass[0].principal_arn == "arn:aws:iam::123456789012:role/ClusterBreakGlass" &&
      aws_eks_access_policy_association.break_glass[0].policy_arn == "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy" &&
      aws_eks_access_policy_association.break_glass[0].access_scope[0].type == "cluster"
    )
    error_message = "Break-glass role must grant AmazonEKSClusterAdminPolicy at cluster scope while routine operator stays scoped."
  }
}

run "storage_identity_is_cluster_scoped_and_secrets_encrypted" {
  command = plan
  variables {
    enable_ebs_csi = true
  }
  assert {
    condition = (
      aws_eks_addon.ebs_csi[0].addon_name == "aws-ebs-csi-driver" &&
      jsondecode(aws_eks_addon.ebs_csi[0].configuration_values).controller.k8sTagClusterId == "storage-test" &&
      aws_iam_role.ebs_csi[0].tags["eks-cluster-name"] == "storage-test" &&
      jsondecode(aws_iam_role.ebs_csi[0].assume_role_policy).Statement[0].Condition.StringEquals["oidc.eks.ap-southeast-1.amazonaws.com/id/TEST:sub"] == "system:serviceaccount:kube-system:ebs-csi-controller-sa" &&
      jsondecode(aws_iam_role.ebs_csi[0].assume_role_policy).Statement[0].Condition.StringEquals["oidc.eks.ap-southeast-1.amazonaws.com/id/TEST:aud"] == "sts.amazonaws.com" &&
      aws_iam_role_policy_attachment.ebs_csi[0].policy_arn == "arn:aws:iam::aws:policy/AmazonEBSCSIDriverEKSClusterScopedPolicy" &&
      aws_kms_key.cluster.enable_key_rotation &&
      contains(aws_eks_cluster.this.encryption_config[0].resources, "secrets") &&
      toset(aws_eks_cluster.this.enabled_cluster_log_types) == toset(["api", "audit", "authenticator", "controllerManager", "scheduler"]) &&
      aws_launch_template.system.block_device_mappings[0].ebs[0].encrypted
    )
    error_message = "Persistent storage and cluster encryption settings must be enforced."
  }
}

run "reject_open_world_operator_cidr" {
  command = plan
  variables {
    operator_access_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.operator_access_cidrs]
}

run "reject_admin_routine_operator_policy" {
  command = plan
  variables {
    operator_access_policy = "AmazonEKSClusterAdminPolicy"
  }
  expect_failures = [var.operator_access_policy]
}

run "reject_duplicate_break_glass_role" {
  command = plan
  variables {
    break_glass_role_arn = "arn:aws:iam::123456789012:role/ClusterOperator"
  }
  expect_failures = [var.break_glass_role_arn]
}
