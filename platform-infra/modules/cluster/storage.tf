resource "aws_iam_role" "ebs_csi" {
  count = var.enable_ebs_csi ? 1 : 0
  name  = "${var.name}-ebs-csi"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = aws_iam_openid_connect_provider.cluster.arn }
      Condition = {
        StringEquals = {
          "${trimprefix(aws_iam_openid_connect_provider.cluster.url, "https://")}:aud" = "sts.amazonaws.com"
          "${trimprefix(aws_iam_openid_connect_provider.cluster.url, "https://")}:sub" = "system:serviceaccount:kube-system:ebs-csi-controller-sa"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  count      = var.enable_ebs_csi ? 1 : 0
  role       = aws_iam_role.ebs_csi[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonEBSCSIDriverPolicyV2"
}

data "aws_eks_addon_version" "ebs_csi" {
  count              = var.enable_ebs_csi ? 1 : 0
  addon_name         = "aws-ebs-csi-driver"
  kubernetes_version = var.kubernetes_version
  most_recent        = true
}

resource "aws_eks_addon" "ebs_csi" {
  count                       = var.enable_ebs_csi ? 1 : 0
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "aws-ebs-csi-driver"
  addon_version               = data.aws_eks_addon_version.ebs_csi[0].version
  service_account_role_arn    = aws_iam_role.ebs_csi[0].arn
  resolve_conflicts_on_update = "PRESERVE"
  depends_on                  = [aws_iam_role_policy_attachment.ebs_csi, aws_eks_node_group.system]
}
