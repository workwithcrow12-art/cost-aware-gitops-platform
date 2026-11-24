variable "name" {
  description = "Name prefix for networking resources."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the VPC."
  type        = string

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr)) && !endswith(var.vpc_cidr, "/0")
    error_message = "Provide a valid non-/0 IPv4 CIDR block for the VPC."
  }
}

variable "az_count" {
  description = "Number of availability zones for EKS."
  type        = number

  validation {
    condition     = contains([2, 3], var.az_count)
    error_message = "Use two or three availability zones."
  }
}

variable "nat_per_az" {
  description = "Create one NAT gateway per availability zone instead of sharing one."
  type        = bool
}

variable "enable_s3_endpoint" {
  description = "Provision a zero-cost S3 Gateway VPC endpoint on private route tables."
  type        = bool
  default     = true
}

variable "enable_interface_endpoints" {
  description = "Provision private interface VPC endpoints for ECR, STS, and CloudWatch Logs."
  type        = bool
  default     = false
}
