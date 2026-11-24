variable "aws_region" {
  description = "AWS region for the EKS environment."
  type        = string
  default     = "ap-southeast-1"
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the environment VPC."
  type        = string
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version."
  type        = string
  default     = "1.35"
}

variable "operator_access_cidrs" {
  description = "Routed operator IPv4 CIDRs for the private Kubernetes API."
  type        = set(string)
  nullable    = false
}

variable "operator_role_arn" {
  description = "Explicit cluster administrator IAM role."
  type        = string
  nullable    = false
}

variable "enable_ebs_csi" {
  description = "Enable the cluster-scoped EBS CSI driver add-on for persistent volume testing."
  type        = bool
  default     = true
}

variable "enable_interface_endpoints" {
  description = "Provision ECR, STS, and CloudWatch Logs interface VPC endpoints."
  type        = bool
  default     = false
}

variable "enable_karpenter" {
  description = "Provision optional Karpenter IAM roles and Spot interruption infrastructure."
  type        = bool
  default     = false
}

variable "budget" {
  description = "Optional environment-filtered monthly AWS Budget."
  type = object({
    monthly_limit_usd         = number
    email                     = string
    additional_emails         = optional(set(string), [])
    subscriber_sns_topic_arns = optional(set(string), [])
  })
  default = null
}

variable "cost_reporting" {
  description = "Optional environment Athena workgroup, CUR catalog, and finops-reporter IRSA role."
  type = object({
    results_s3           = optional(string)
    results_bucket_owner = optional(string)
    enable_reporter      = optional(bool, false)
    cur_catalog = optional(object({
      database_name    = string
      table_name       = string
      data_s3          = string
      partitioned      = optional(bool, true)
      projection_years = optional(string, "2024,2030")
    }))
  })
  default = null
}

variable "github_oidc" {
  description = "Optional environment-scoped GitHub Actions OIDC IAM roles."
  type = object({
    provider_arn             = optional(string)
    permissions_boundary_arn = optional(string)
    roles = map(object({
      subjects   = set(string)
      policy_arn = string
    }))
  })
  default = null
}
