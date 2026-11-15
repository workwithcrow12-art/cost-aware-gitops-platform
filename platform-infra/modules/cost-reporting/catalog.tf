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
  parameters    = { classification = "parquet", EXTERNAL = "TRUE" }

  storage_descriptor {
    location      = var.cur_catalog.data_s3
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "line_item_usage_start_date"
      type = "timestamp"
    }
    columns {
      name = "line_item_product_code"
      type = "string"
    }
    columns {
      name = "line_item_unblended_cost"
      type = "double"
    }
    columns {
      name = "resource_tags_user_env"
      type = "string"
    }
    columns {
      name = "resource_tags_user_team"
      type = "string"
    }
  }
}
