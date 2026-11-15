locals {
  issuer       = "token.actions.githubusercontent.com"
  provider_arn = var.provider_arn == null ? aws_iam_openid_connect_provider.github[0].arn : var.provider_arn
}

resource "aws_iam_openid_connect_provider" "github" {
  count = var.provider_arn == null ? 1 : 0

  url            = "https://${local.issuer}"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "github" {
  for_each = var.roles

  name                 = "${var.name_prefix}-${each.key}"
  permissions_boundary = var.permissions_boundary_arn
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRoleWithWebIdentity"
      Effect    = "Allow"
      Principal = { Federated = local.provider_arn }
      Condition = {
        StringEquals = {
          "${local.issuer}:aud" = "sts.amazonaws.com"
          "${local.issuer}:sub" = each.value.subjects
        }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "github" {
  for_each = var.roles

  role       = aws_iam_role.github[each.key].name
  policy_arn = each.value.policy_arn
}
