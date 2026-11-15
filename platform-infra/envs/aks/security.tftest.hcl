mock_provider "azurerm" {}

variables {
  subscription_id          = "11111111-1111-1111-1111-111111111111"
  tenant_id                = "22222222-2222-2222-2222-222222222222"
  operator_group_object_id = "33333333-3333-3333-3333-333333333333"
}

run "private_cluster_with_rbac_and_cost_tags" {
  command = plan
  assert {
    condition = (
      azurerm_kubernetes_cluster.this.private_cluster_enabled &&
      !azurerm_kubernetes_cluster.this.private_cluster_public_fqdn_enabled &&
      azurerm_kubernetes_cluster.this.local_account_disabled &&
      azurerm_kubernetes_cluster.this.azure_active_directory_role_based_access_control[0].azure_rbac_enabled &&
      azurerm_kubernetes_cluster.this.network_profile[0].network_policy == "calico" &&
      azurerm_kubernetes_cluster.this.workload_identity_enabled &&
      azurerm_kubernetes_cluster.this.tags["env"] == "nonprod" &&
      azurerm_kubernetes_cluster.this.default_node_pool[0].tags["team"] == "platform" &&
      azurerm_role_assignment.operator.role_definition_name == "Azure Kubernetes Service RBAC Cluster Admin"
    )
    error_message = "AKS must retain private API, Entra RBAC, policy enforcement, workload identity and node cost tags."
  }
}

run "reject_missing_cost_tags" {
  command = plan
  variables {
    cost_tags = { env = "nonprod" }
  }
  expect_failures = [var.cost_tags]
}
