variable "name" {
  description = "Name of the account-wide monthly budget."
  type        = string
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
  description = "Email address that receives budget notifications."
  type        = string
}
