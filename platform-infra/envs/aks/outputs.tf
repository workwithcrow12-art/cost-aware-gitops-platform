output "cluster_name" {
  value = azurerm_kubernetes_cluster.this.name
}

output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "kube_context" {
  value = var.name
}

output "get_credentials_command" {
  value = "az aks get-credentials --subscription ${var.subscription_id} --resource-group ${var.name} --name ${var.name} --context ${var.name}"
}
