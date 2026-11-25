variable "aws_region" {
  description = "AWS region for the EKS environment."
  type        = string
  default     = "ap-southeast-1"
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the environment VPC."
  type        = string
}

variable "nat_per_az" {
  description = "Provision one NAT gateway per availability zone (~$129/month fixed in ap-southeast-1 across 3 AZs) for AZ-isolated egress; set false (~$43/month) only when accepting cross-AZ egress fees and single-AZ NAT failure blast radius."
  type        = bool
  default     = true
  nullable    = false
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

  validation {
    condition = length(var.operator_access_cidrs) > 0 && alltrue([
      for cidr in var.operator_access_cidrs : can(cidrnetmask(cidr)) && !endswith(cidr, "/0")
    ])
    error_message = "Provide at least one valid operator IPv4 CIDR and exclude /0 networks."
  }
}

variable "operator_role_arn" {
  description = "Explicit IAM role granted routine Kubernetes operator access."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^arn:aws(-[a-z]+)*:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$", var.operator_role_arn))
    error_message = "Provide an IAM role ARN, not an AWS STS session ARN or IAM user ARN."
  }
}

variable "operator_access_policy" {
  description = "EKS cluster access policy associated with operator_role_arn for routine read or edit access."
  type        = string
  default     = "AmazonEKSViewPolicy"
  nullable    = false

  validation {
    condition     = contains(["AmazonEKSViewPolicy", "AmazonEKSEditPolicy"], var.operator_access_policy)
    error_message = "Routine operator_access_policy must be AmazonEKSViewPolicy or AmazonEKSEditPolicy."
  }
}

variable "break_glass_role_arn" {
  description = "Optional distinct IAM role granted AmazonEKSClusterAdminPolicy for initial Argo CD bootstrap and emergency break-glass recovery."
  type        = string
  default     = null

  validation {
    condition = var.break_glass_role_arn == null || (
      can(regex("^arn:aws(-[a-z]+)*:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$", var.break_glass_role_arn)) &&
      var.break_glass_role_arn != var.operator_role_arn
    )
    error_message = "When set, break_glass_role_arn must be a valid IAM role ARN distinct from operator_role_arn."
  }
}

variable "enable_ebs_csi" {
  description = "Enable the cluster-scoped EBS CSI driver add-on for persistent workloads."
  type        = bool
  default     = true
}

variable "enable_interface_endpoints" {
  description = "Provision ECR, STS, and CloudWatch Logs interface VPC endpoints."
  type        = bool
  default     = false
}

variable "enable_karpenter" {
  description = "Provision optional Karpenter IAM roles and interruption infrastructure."
  type        = bool
  default     = false
}

variable "budget" {
  description = "Required environment-filtered monthly AWS Budget for production."
  type = object({
    monthly_limit_usd         = number
    email                     = string
    additional_emails         = optional(set(string), [])
    subscriber_sns_topic_arns = optional(set(string), [])
  })
  nullable = false

  validation {
    condition = (
      var.budget.monthly_limit_usd > 0 &&
      can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.budget.email))
    )
    error_message = "Production budget requires a monthly_limit_usd greater than zero and a valid notification email."
  }
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
