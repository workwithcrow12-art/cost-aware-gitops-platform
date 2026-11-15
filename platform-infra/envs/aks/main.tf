provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
  tenant_id       = var.tenant_id
}

resource "azurerm_resource_group" "this" {
  name     = var.name
  location = var.location
  tags     = var.cost_tags
}

resource "azurerm_virtual_network" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = ["10.60.0.0/16"]
  tags                = var.cost_tags
}

resource "azurerm_subnet" "nodes" {
  name                 = "nodes"
  resource_group_name  = azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.60.0.0/20"]
}

resource "azurerm_user_assigned_identity" "cluster" {
  name                = "${var.name}-cluster"
  resource_group_name = azurerm_resource_group.this.name
  location            = var.location
  tags                = var.cost_tags
}

resource "azurerm_role_assignment" "network" {
  scope                = azurerm_subnet.nodes.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.cluster.principal_id
}

resource "azurerm_kubernetes_cluster" "this" {
  name                                = var.name
  location                            = var.location
  resource_group_name                 = azurerm_resource_group.this.name
  dns_prefix                          = var.name
  private_cluster_enabled             = true
  private_cluster_public_fqdn_enabled = false
  local_account_disabled              = true
  role_based_access_control_enabled   = true
  oidc_issuer_enabled                 = true
  workload_identity_enabled           = true
  automatic_upgrade_channel           = "patch"
  tags                                = var.cost_tags

  default_node_pool {
    name                        = "system"
    temporary_name_for_rotation = "systemtemp"
    node_count                  = 2
    vm_size                     = "Standard_D4s_v5"
    os_disk_size_gb             = 30
    vnet_subnet_id              = azurerm_subnet.nodes.id
    node_public_ip_enabled      = false
    tags                        = var.cost_tags
  }
  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.cluster.id]
  }
  azure_active_directory_role_based_access_control {
    tenant_id          = var.tenant_id
    azure_rbac_enabled = true
  }
  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_policy      = "calico"
    pod_cidr            = "10.64.0.0/16"
    service_cidr        = "10.65.0.0/20"
    dns_service_ip      = "10.65.0.10"
    outbound_type       = "loadBalancer"
  }
  depends_on = [azurerm_role_assignment.network]
}

resource "azurerm_role_assignment" "operator" {
  scope                = azurerm_kubernetes_cluster.this.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = var.operator_group_object_id
}

resource "azurerm_role_assignment" "credentials" {
  scope                = azurerm_kubernetes_cluster.this.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = var.operator_group_object_id
}
