variable "name" {
  description = "Name prefix for networking resources."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the VPC."
  type        = string
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
