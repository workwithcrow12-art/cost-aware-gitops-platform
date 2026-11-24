variable "name_prefix" {
  description = "Name prefix for GitHub Actions IAM roles."
  type        = string

  validation {
    condition     = trimspace(var.name_prefix) != ""
    error_message = "Provide a non-empty role name prefix."
  }
}

variable "provider_arn" {
  description = "Existing GitHub OIDC provider ARN, or null to create one."
  type        = string
  default     = null

  validation {
    condition     = var.provider_arn == null || can(regex("^arn:aws(-[a-z]+)*:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.provider_arn))
    error_message = "Provide a valid GitHub Actions IAM OIDC provider ARN or null."
  }
}

variable "permissions_boundary_arn" {
  description = "Optional IAM policy ARN defining the maximum privileges of these roles."
  type        = string
  default     = null

  validation {
    condition     = var.permissions_boundary_arn == null || can(regex("^arn:aws(-[a-z]+)*:iam::([0-9]{12}|aws):policy/.+$", var.permissions_boundary_arn))
    error_message = "Provide a valid IAM permissions boundary policy ARN or null."
  }
}

variable "roles" {
  description = "Exact GitHub OIDC subjects and an existing IAM permission policy for each role."
  type = map(object({
    subjects   = set(string)
    policy_arn = string
  }))

  validation {
    condition = length(var.roles) > 0 && alltrue(flatten([
      for role in values(var.roles) : [
        length(role.subjects) > 0,
        can(regex("^arn:aws(-[a-z]+)*:iam::([0-9]{12}|aws):policy/.+$", role.policy_arn)),
        [
          for sub in role.subjects : (
            !strcontains(sub, "*") &&
            !strcontains(sub, "?") &&
            can(regex("^repo:[A-Za-z0-9_.-]+(@[0-9]+)?/[A-Za-z0-9_.-]+(@[0-9]+)?:(ref:refs/(heads|tags)/[^:*?]+|environment:[^:*?]+)(:.+)?$", sub))
          )
        ]
      ]
    ]))
    error_message = "Each role must attach a valid IAM policy ARN and specify at least one exact, wildcard-free GitHub OIDC subject scoped to a branch, tag, or environment."
  }
}
