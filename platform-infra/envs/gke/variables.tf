variable "project_id" {
  description = "Existing billing-enabled Google Cloud project."
  type        = string
}

variable "name" {
  description = "Name of the GKE cluster and network resources."
  type        = string
  default     = "cost-aware-gke"
}

variable "region" {
  description = "Google Cloud region for the GKE network and NAT router."
  type        = string
  default     = "asia-southeast1"
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

variable "subnet_cidr" {
  description = "Primary IPv4 CIDR range for the GKE node subnetwork."
  type        = string
  default     = "10.40.0.0/20"

  validation {
    condition     = can(cidrnetmask(var.subnet_cidr)) && !endswith(var.subnet_cidr, "/0")
    error_message = "Provide a valid non-/0 IPv4 CIDR for subnet_cidr."
  }
}

variable "node_count" {
  description = "Number of system node pool instances (set 2 for nonprod labs, >= 3 for prod)."
  type        = number
  default     = 2

  validation {
    condition     = var.node_count >= 1
    error_message = "node_count must be at least 1."
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
  description = "Cost allocation labels applied to the GKE cluster and worker nodes."
  type        = map(string)
  default     = { team = "platform", env = "nonprod", project = "cost-aware-gitops", owner = "platform" }

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
