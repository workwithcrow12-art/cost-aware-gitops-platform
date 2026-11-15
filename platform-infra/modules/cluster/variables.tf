variable "name" {
  description = "EKS cluster name."
  type        = string
}

variable "enable_ebs_csi" {
  description = "Install the EBS CSI driver with a scoped IRSA role for persistent workloads."
  type        = bool
  default     = false
}

variable "kubernetes_version" {
  description = "EKS Kubernetes minor version."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets across at least two availability zones."
  type        = list(string)
}

variable "operator_access_cidrs" {
  description = "Routed operator IPv4 CIDRs allowed to reach the private EKS endpoint on TCP port 443."
  type        = set(string)
  nullable    = false

  validation {
    condition = length(var.operator_access_cidrs) > 0 && alltrue([
      for cidr in var.operator_access_cidrs : can(cidrnetmask(cidr)) && !endswith(cidr, "/0")
    ])
    error_message = "Provide at least one valid operator IPv4 CIDR and exclude /0 networks."
  }
}

variable "operator_role_arn" {
  description = "Explicit IAM role that can administer Kubernetes."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^arn:aws(-[a-z]+)*:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$", var.operator_role_arn))
    error_message = "Provide an IAM role ARN, not an AWS STS session ARN or IAM user ARN."
  }
}

variable "capacity_type" {
  description = "EKS managed node group capacity type."
  type        = string
}

variable "instance_types" {
  description = "Compatible x86_64 instance types for the node group."
  type        = list(string)
}

variable "node_count" {
  description = "Desired number of nodes in the system node group."
  type        = number
}

variable "cost_tags" {
  description = "Cost allocation tags applied to worker EC2 instances and their EBS volumes."
  type        = map(string)
  nullable    = false

  validation {
    condition = alltrue([
      for key in ["team", "env", "project", "owner"] : trimspace(lookup(var.cost_tags, key, "")) != ""
    ])
    error_message = "Worker cost tags must include non-empty team, env, project and owner values."
  }
}
