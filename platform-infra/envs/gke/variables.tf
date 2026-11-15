variable "project_id" {
  description = "Existing billing-enabled Google Cloud project."
  type        = string
}

variable "name" {
  type    = string
  default = "cost-aware-gke"
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

variable "zone" {
  description = "One zone in region; the lab uses a zonal cluster to avoid multiplying node costs."
  type        = string
  default     = "asia-southeast1-a"
  validation {
    condition     = startswith(var.zone, "${var.region}-")
    error_message = "zone must belong to region."
  }
}

variable "operator_member" {
  description = "Explicit IAM member allowed to administer this lab project's clusters (user: or group:)."
  type        = string
  validation {
    condition     = can(regex("^(user|group):[^@ ]+@[^ ]+$", var.operator_member))
    error_message = "Use a named user:email or group:email IAM member."
  }
}

variable "operator_access_cidrs" {
  description = "Operator IPv4 ranges routed to the private control plane through VPN or a bastion."
  type        = set(string)
  validation {
    condition = length(var.operator_access_cidrs) > 0 && alltrue([
      for cidr in var.operator_access_cidrs : can(cidrnetmask(cidr)) && !endswith(cidr, "/0")
    ])
    error_message = "Provide routed operator IPv4 CIDRs; /0 is forbidden."
  }
}

variable "cost_tags" {
  type    = map(string)
  default = { team = "platform", env = "nonprod", project = "cost-aware-gitops", owner = "platform" }
  validation {
    condition = alltrue([
      for key in ["team", "env", "project", "owner"] : can(regex("^[a-z0-9_-]{1,63}$", lookup(var.cost_tags, key, "")))
    ])
    error_message = "Include team, env, project and owner with valid non-empty Google label values."
  }
}

variable "deletion_protection" {
  description = "Apply false explicitly before destroying this lab cluster."
  type        = bool
  default     = true
}
