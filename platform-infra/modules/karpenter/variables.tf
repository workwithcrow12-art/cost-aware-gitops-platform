variable "cluster_name" {
  description = "Name of the EKS cluster managed by Karpenter."
  type        = string

  validation {
    condition     = trimspace(var.cluster_name) != ""
    error_message = "Provide a non-empty EKS cluster name."
  }
}

variable "oidc_provider_arn" {
  description = "IAM OIDC provider ARN of the EKS cluster."
  type        = string

  validation {
    condition     = can(regex("^arn:aws(-[a-z]+)*:iam::[0-9]{12}:oidc-provider/.+$", var.oidc_provider_arn))
    error_message = "Provide a valid IAM OIDC provider ARN."
  }
}

variable "oidc_issuer_url" {
  description = "HTTPS OIDC issuer URL of the EKS cluster without a trailing slash."
  type        = string

  validation {
    condition     = startswith(var.oidc_issuer_url, "https://") && !endswith(var.oidc_issuer_url, "/")
    error_message = "Provide an HTTPS OIDC issuer URL without a trailing slash."
  }
}

variable "namespace" {
  description = "Kubernetes namespace running the Karpenter controller."
  type        = string
  default     = "kube-system"
}

variable "service_account" {
  description = "Kubernetes ServiceAccount name for the Karpenter controller."
  type        = string
  default     = "karpenter"
}
