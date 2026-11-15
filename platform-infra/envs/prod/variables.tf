variable "aws_region" {
  description = "AWS region for the EKS environment."
  type        = string
  default     = "ap-southeast-1"
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the environment VPC."
  type        = string
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version."
  type        = string
  default     = "1.35"
}

variable "operator_access_cidrs" {
  description = "Routed operator IPv4 CIDRs for the private Kubernetes API."
  type        = set(string)
  nullable    = false
}

variable "operator_role_arn" {
  description = "Explicit cluster administrator IAM role."
  type        = string
  nullable    = false
}
