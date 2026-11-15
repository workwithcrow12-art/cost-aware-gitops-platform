mock_provider "aws" {
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_eks_addon_version" {
    defaults = { version = "v1.21.0-eksbuild.1" }
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

run "storage_disabled_by_default" {
  command = plan
  assert {
    condition     = length(aws_eks_addon.ebs_csi) == 0 && length(aws_iam_role.ebs_csi) == 0
    error_message = "Nonprod must not acquire an unused CSI driver or role."
  }
}

run "storage_identity_is_scoped" {
  command = plan
  variables {
    enable_ebs_csi = true
  }
  assert {
    condition = (
      aws_eks_addon.ebs_csi[0].addon_name == "aws-ebs-csi-driver" &&
      jsondecode(aws_iam_role.ebs_csi[0].assume_role_policy).Statement[0].Condition.StringEquals["oidc.eks.ap-southeast-1.amazonaws.com/id/TEST:sub"] == "system:serviceaccount:kube-system:ebs-csi-controller-sa" &&
      jsondecode(aws_iam_role.ebs_csi[0].assume_role_policy).Statement[0].Condition.StringEquals["oidc.eks.ap-southeast-1.amazonaws.com/id/TEST:aud"] == "sts.amazonaws.com" &&
      aws_iam_role_policy_attachment.ebs_csi[0].policy_arn == "arn:aws:iam::aws:policy/AmazonEBSCSIDriverPolicyV2"
    )
    error_message = "Persistent storage requires the CSI addon and an audience/ServiceAccount-bound role."
  }
}
