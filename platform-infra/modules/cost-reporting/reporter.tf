locals {
  aws_arn_prefix = "arn:${data.aws_partition.current.partition}"
  catalog_arn    = "${local.aws_arn_prefix}:glue:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}"
  results_parts  = split("/", trimprefix(local.results_s3, "s3://"))
  cur_parts      = var.cur_catalog == null ? [] : split("/", trimprefix(var.cur_catalog.data_s3, "s3://"))
}

resource "aws_iam_role" "reporter" {
  count = var.reporter == null ? 0 : 1
  name  = "${var.name}-reporter"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = var.reporter.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${trimprefix(var.reporter.oidc_issuer_url, "https://")}:aud" = "sts.amazonaws.com"
          "${trimprefix(var.reporter.oidc_issuer_url, "https://")}:sub" = "system:serviceaccount:finops:finops-reporter"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "reporter" {
  count = var.reporter == null ? 0 : 1
  name  = "query-cur"
  role  = aws_iam_role.reporter[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution", "athena:GetWorkGroup"]
        Resource = "${local.aws_arn_prefix}:athena:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:workgroup/${var.name}"
      },
      {
        Effect = "Allow"
        Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions"]
        Resource = [
          "${local.catalog_arn}:catalog",
          "${local.catalog_arn}:database/${var.cur_catalog.database_name}",
          "${local.catalog_arn}:table/${var.cur_catalog.database_name}/${var.cur_catalog.table_name}"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${local.aws_arn_prefix}:s3:::${trimprefix(var.cur_catalog.data_s3, "s3://")}*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"]
        Resource = "${local.aws_arn_prefix}:s3:::${trimprefix(local.results_s3, "s3://")}*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetBucketLocation"]
        Resource = ["${local.aws_arn_prefix}:s3:::${local.cur_parts[0]}", "${local.aws_arn_prefix}:s3:::${local.results_parts[0]}"]
      },
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = "${local.aws_arn_prefix}:s3:::${local.cur_parts[0]}"
        Condition = { StringLike = { "s3:prefix" = ["${join("/", slice(local.cur_parts, 1, length(local.cur_parts)))}*"] } }
      },
      {
        Effect    = "Allow"
        Action    = ["s3:ListBucket"]
        Resource  = "${local.aws_arn_prefix}:s3:::${local.results_parts[0]}"
        Condition = { StringLike = { "s3:prefix" = ["${join("/", slice(local.results_parts, 1, length(local.results_parts)))}*"] } }
      }
    ]
  })
}
