terraform {
  required_version = "~> 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.15.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      team    = "platform"
      env     = "shared"
      project = "cost-aware-gitops"
      owner   = "platform"
    }
  }
}

variable "aws_region" {
  description = "AWS region of the Terraform state bucket."
  type        = string
  default     = "ap-southeast-1"
}

variable "state_bucket_name" {
  description = "Globally unique S3 bucket name for Terraform state."
  type        = string
}

variable "budget_email" {
  description = "Email address that receives the account-wide budget notifications."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Account-wide monthly AWS budget in US dollars."
  type        = number
}

variable "athena_results_s3" {
  description = "Optional existing S3 results prefix for the FinOps Athena workgroup."
  type        = string
  default     = null
}

variable "athena_results_bucket_owner" {
  description = "AWS account ID owning the Athena results bucket, defaulting to this AWS account."
  type        = string
  default     = null
}

variable "athena_cur_catalog" {
  description = "Optional legacy CUR Parquet catalog; also enables managed Athena results when athena_results_s3 is null."
  type = object({
    database_name = string
    table_name    = string
    data_s3       = string
  })
  default = null
}

variable "athena_reporter" {
  description = "Optional EKS OIDC identity for finops/finops-reporter; requires athena_cur_catalog."
  type = object({
    oidc_provider_arn = string
    oidc_issuer_url   = string
  })
  default = null
  validation {
    condition     = var.athena_reporter == null || var.athena_cur_catalog != null
    error_message = "Configure athena_cur_catalog before enabling athena_reporter."
  }
}

variable "github_actions" {
  description = "Optional GitHub repository and existing IAM permission policies for the CI roles."
  type = object({
    repository               = string
    repository_owner_id      = string
    repository_id            = string
    oidc_provider_arn        = optional(string)
    permissions_boundary_arn = optional(string)
    plan_policy_arn          = string
    apply_policy_arns        = map(string)
  })
  default = null

  validation {
    condition = var.github_actions == null ? true : (
      can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_actions.repository)) &&
      can(regex("^[0-9]+$", var.github_actions.repository_owner_id)) &&
      can(regex("^[0-9]+$", var.github_actions.repository_id)) &&
      toset(keys(var.github_actions.apply_policy_arns)) == toset(["nonprod", "prod"])
    )
    error_message = "Provide the GitHub owner/repository, numeric owner and repository IDs, and apply policy ARNs for nonprod and prod."
  }
}

locals {
  github_repository = var.github_actions == null ? [] : split("/", var.github_actions.repository)
  github_subject = var.github_actions == null ? null : format(
    "repo:%s@%s/%s@%s",
    local.github_repository[0], var.github_actions.repository_owner_id,
    local.github_repository[1], var.github_actions.repository_id,
  )
  github_workflows = var.github_actions == null ? null : "${var.github_actions.repository}/.github/workflows"
}

module "budget" {
  source            = "../../modules/budgets"
  name              = "cost-aware-platform-monthly"
  monthly_limit_usd = var.monthly_budget_usd
  email             = var.budget_email
}

module "cost_reporting" {
  count = var.athena_results_s3 != null || var.athena_cur_catalog != null ? 1 : 0

  source               = "../../modules/cost-reporting"
  name                 = "cost-aware-finops"
  results_s3           = var.athena_results_s3
  results_bucket_owner = var.athena_results_bucket_owner
  cur_catalog          = var.athena_cur_catalog
  reporter             = var.athena_reporter
}

module "github_actions" {
  count = var.github_actions == null ? 0 : 1

  source                   = "../../modules/iam-github-oidc"
  name_prefix              = "cost-aware-terraform"
  provider_arn             = var.github_actions.oidc_provider_arn
  permissions_boundary_arn = var.github_actions.permissions_boundary_arn
  roles = merge({
    plan = {
      policy_arn = var.github_actions.plan_policy_arn
      subjects = [
        "${local.github_subject}:ref:refs/heads/main:workflow_ref:${local.github_workflows}/drift-detection.yml@refs/heads/main",
        "${local.github_subject}:ref:refs/heads/main:workflow_ref:${local.github_workflows}/terraform-apply.yml@refs/heads/main",
      ]
    }
    }, {
    for environment, policy_arn in var.github_actions.apply_policy_arns : "apply-${environment}" => {
      policy_arn = policy_arn
      subjects   = ["${local.github_subject}:environment:${environment}:workflow_ref:${local.github_workflows}/terraform-apply.yml@refs/heads/main"]
    }
  })
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "state_tls" {
  bucket = aws_s3_bucket.state.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
