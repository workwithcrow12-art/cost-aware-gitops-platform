variable "subscription_id" {
  description = "Existing Azure subscription ID."
  type        = string
}

variable "tenant_id" {
  description = "Microsoft Entra tenant ID."
  type        = string
}

variable "operator_group_object_id" {
  description = "Microsoft Entra group allowed to administer this cluster."
  type        = string
}

variable "name" {
  type    = string
  default = "cost-aware-aks"
}

variable "location" {
  type    = string
  default = "southeastasia"
}

variable "cost_tags" {
  type    = map(string)
  default = { team = "platform", env = "nonprod", project = "cost-aware-gitops", owner = "platform" }
  validation {
    condition = alltrue([
      for key in ["team", "env", "project", "owner"] : trimspace(lookup(var.cost_tags, key, "")) != ""
    ])
    error_message = "Include non-empty team, env, project and owner cost tags."
  }
}
