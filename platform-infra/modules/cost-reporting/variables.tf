variable "name" {
  description = "Athena workgroup name."
  type        = string
}

variable "results_s3" {
  description = "Existing S3 results prefix in the Athena region, or null to create a private encrypted results bucket."
  type        = string
  default     = null

  validation {
    condition     = var.results_s3 == null ? true : can(regex("^s3://[^/]+/.+", var.results_s3))
    error_message = "Provide an S3 URI with a bucket and prefix, such as s3://results-bucket/finops/."
  }
}

variable "cur_catalog" {
  description = "Optional catalog for an existing legacy CUR Parquet data prefix (not manifests or CSV)."
  type = object({
    database_name = string
    table_name    = string
    data_s3       = string
  })
  default = null

  validation {
    condition = var.cur_catalog == null ? true : (
      can(regex("^[a-z_][a-z0-9_]*$", var.cur_catalog.database_name)) &&
      can(regex("^[a-z_][a-z0-9_]*$", var.cur_catalog.table_name)) &&
      can(regex("^s3://[^/]+/.+/$", var.cur_catalog.data_s3))
    )
    error_message = "Use lowercase SQL identifiers and a CUR Parquet S3 prefix ending in /."
  }
}

variable "reporter" {
  description = "Optional EKS OIDC identity for the finops/finops-reporter ServiceAccount; requires cur_catalog."
  type = object({
    oidc_provider_arn = string
    oidc_issuer_url   = string
  })
  default = null

  validation {
    condition     = var.reporter == null || var.cur_catalog != null
    error_message = "Configure cur_catalog before enabling the reporter IAM role."
  }

  validation {
    condition = var.reporter == null ? true : (
      startswith(var.reporter.oidc_issuer_url, "https://") &&
      !endswith(var.reporter.oidc_issuer_url, "/") &&
      can(regex("^arn:aws(-[a-z]+)*:iam::[0-9]{12}:oidc-provider/.+$", var.reporter.oidc_provider_arn)) &&
      endswith(var.reporter.oidc_provider_arn, ":oidc-provider/${trimprefix(var.reporter.oidc_issuer_url, "https://")}")
    )
    error_message = "Supply the matching IAM OIDC provider ARN and HTTPS issuer URL without a trailing slash."
  }
}

variable "results_bucket_owner" {
  description = "Expected AWS account ID owning the Athena results bucket."
  type        = string
  default     = null

  validation {
    condition     = var.results_bucket_owner == null || can(regex("^[0-9]{12}$", var.results_bucket_owner))
    error_message = "Use a 12-digit AWS account ID for the results bucket owner."
  }
}
