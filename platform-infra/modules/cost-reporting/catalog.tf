locals {
  cur_columns = [
    { name = "identity_line_item_id", type = "string" },
    { name = "bill_billing_period_start_date", type = "timestamp" },
    { name = "bill_billing_period_end_date", type = "timestamp" },
    { name = "line_item_usage_account_id", type = "string" },
    { name = "line_item_line_item_type", type = "string" },
    { name = "line_item_usage_start_date", type = "timestamp" },
    { name = "line_item_usage_end_date", type = "timestamp" },
    { name = "line_item_product_code", type = "string" },
    { name = "line_item_usage_type", type = "string" },
    { name = "line_item_operation", type = "string" },
    { name = "line_item_resource_id", type = "string" },
    { name = "line_item_unblended_cost", type = "double" },
    { name = "line_item_blended_cost", type = "double" },
    { name = "pricing_public_on_demand_cost", type = "double" },
    { name = "product_region", type = "string" },
    { name = "resource_tags_user_env", type = "string" },
    { name = "resource_tags_user_team", type = "string" },
    { name = "resource_tags_user_project", type = "string" },
    { name = "resource_tags_user_owner", type = "string" },
  ]
}

resource "aws_s3_bucket" "results" {
  count         = var.results_s3 == null ? 1 : 0
  bucket_prefix = "finops-athena-"
}

resource "aws_s3_bucket_public_access_block" "results" {
  count                   = var.results_s3 == null ? 1 : 0
  bucket                  = aws_s3_bucket.results[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "results" {
  count  = var.results_s3 == null ? 1 : 0
  bucket = aws_s3_bucket.results[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "results" {
  count  = var.results_s3 == null ? 1 : 0
  bucket = aws_s3_bucket.results[0].id
  rule {
    id     = "expire-transient-query-results"
    status = "Enabled"
    filter {}
    expiration {
      days = 30
    }
  }
}

resource "aws_s3_bucket_policy" "results_tls" {
  count  = var.results_s3 == null ? 1 : 0
  bucket = aws_s3_bucket.results[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.results[0].arn, "${aws_s3_bucket.results[0].arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

resource "aws_glue_catalog_database" "cur" {
  count = var.cur_catalog == null ? 0 : 1
  name  = var.cur_catalog.database_name
}

resource "aws_glue_catalog_table" "cur" {
  count         = var.cur_catalog == null ? 0 : 1
  name          = var.cur_catalog.table_name
  database_name = aws_glue_catalog_database.cur[0].name
  table_type    = "EXTERNAL_TABLE"

  parameters = merge(
    { classification = "parquet", EXTERNAL = "TRUE" },
    var.cur_catalog.partitioned ? {
      "projection.enabled"        = "true"
      "projection.year.type"      = "integer"
      "projection.year.range"     = var.cur_catalog.projection_years
      "projection.month.type"     = "integer"
      "projection.month.range"    = "1,12"
      "storage.location.template" = "${var.cur_catalog.data_s3}year=$${year}/month=$${month}/"
    } : {}
  )

  dynamic "partition_keys" {
    for_each = var.cur_catalog.partitioned ? ["year", "month"] : []
    content {
      name = partition_keys.value
      type = "string"
    }
  }

  storage_descriptor {
    location      = var.cur_catalog.data_s3
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    dynamic "columns" {
      for_each = local.cur_columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}
