variable "name_prefix" {
  description = "Name prefix for GitHub Actions IAM roles."
  type        = string
}

variable "provider_arn" {
  description = "Existing GitHub OIDC provider ARN, or null to create one."
  type        = string
  default     = null
}

variable "permissions_boundary_arn" {
  description = "Optional IAM policy ARN defining the maximum privileges of these roles."
  type        = string
  default     = null
}

variable "roles" {
  description = "Exact GitHub OIDC subjects and an existing IAM permission policy for each role."
  type = map(object({
    subjects   = set(string)
    policy_arn = string
  }))
}
