variable "name" {
  description = "Name of the monthly AWS budget."
  type        = string

  validation {
    condition     = trimspace(var.name) != ""
    error_message = "Provide a non-empty budget name."
  }
}

variable "monthly_limit_usd" {
  description = "Monthly limit in US dollars."
  type        = number

  validation {
    condition     = var.monthly_limit_usd > 0
    error_message = "The budget limit must be greater than zero."
  }
}

variable "email" {
  description = "Primary email address that receives budget notifications."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.email))
    error_message = "Provide a valid subscriber email address."
  }
}

variable "additional_emails" {
  description = "Optional additional email addresses receiving budget notifications."
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for addr in var.additional_emails : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", addr))
    ])
    error_message = "Every additional subscriber email must be a valid email address."
  }
}

variable "subscriber_sns_topic_arns" {
  description = "Optional SNS topic ARNs receiving budget notifications."
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for arn in var.subscriber_sns_topic_arns : can(regex("^arn:aws(-[a-z]+)*:sns:[a-z0-9-]+:[0-9]{12}:.+$", arn))
    ])
    error_message = "Every SNS subscriber must be a valid AWS SNS topic ARN."
  }
}

variable "cost_filters" {
  description = "Optional AWS Budgets cost filters (for example TagKeyValue = [\"user:env$nonprod\"])."
  type        = map(list(string))
  default     = {}

  validation {
    condition = alltrue([
      for values in values(var.cost_filters) : length(values) > 0
    ])
    error_message = "Each cost filter entry must specify at least one value."
  }
}

variable "cost_types" {
  description = "Optional AWS Budgets cost calculation flags."
  type = object({
    include_credit  = optional(bool, false)
    include_refund  = optional(bool, false)
    include_support = optional(bool, true)
    include_tax     = optional(bool, true)
    use_amortized   = optional(bool, false)
  })
  default = null
}
