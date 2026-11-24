variable "subscription_id" {
  description = "Existing Azure subscription ID."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "Provide a valid UUID for subscription_id."
  }
}

variable "tenant_id" {
  description = "Microsoft Entra tenant ID."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.tenant_id))
    error_message = "Provide a valid UUID for tenant_id."
  }
}

variable "operator_group_object_id" {
  description = "Microsoft Entra group object ID allowed to administer this cluster."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.operator_group_object_id))
    error_message = "Provide a valid UUID for operator_group_object_id."
  }
}

variable "name" {
  description = "Name of the AKS cluster and resource group."
  type        = string
  default     = "cost-aware-aks"
}

variable "location" {
  description = "Azure region for AKS resources."
  type        = string
  default     = "southeastasia"
}

variable "vnet_cidr" {
  description = "IPv4 CIDR block for the AKS virtual network."
  type        = string
  default     = "10.60.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vnet_cidr)) && !endswith(var.vnet_cidr, "/0")
    error_message = "Provide a valid non-/0 IPv4 CIDR for vnet_cidr."
  }
}

variable "subnet_cidr" {
  description = "IPv4 CIDR block for the AKS node subnet."
  type        = string
  default     = "10.60.0.0/20"

  validation {
    condition     = can(cidrnetmask(var.subnet_cidr)) && !endswith(var.subnet_cidr, "/0")
    error_message = "Provide a valid non-/0 IPv4 CIDR for subnet_cidr."
  }
}

variable "node_count" {
  description = "Number of system node pool VMs (set 2 for nonprod labs, >= 3 for prod)."
  type        = number
  default     = 2

  validation {
    condition     = var.node_count >= 1
    error_message = "node_count must be at least 1."
  }
}

variable "cost_tags" {
  description = "Cost allocation tags applied to Azure resources and AKS node pools."
  type        = map(string)
  default     = { team = "platform", env = "nonprod", project = "cost-aware-gitops", owner = "platform" }

  validation {
    condition = alltrue([
      for key in ["team", "env", "project", "owner"] : trimspace(lookup(var.cost_tags, key, "")) != ""
    ])
    error_message = "Include non-empty team, env, project and owner cost tags."
  }
}
