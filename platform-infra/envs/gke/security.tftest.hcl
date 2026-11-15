mock_provider "google" {}

variables {
  project_id            = "cost-aware-test"
  operator_member       = "group:platform@example.com"
  operator_access_cidrs = ["10.50.0.0/24"]
}

run "private_cluster_with_policy_and_cost_labels" {
  command = plan
  assert {
    condition = (
      google_container_cluster.this.private_cluster_config[0].enable_private_endpoint &&
      google_container_cluster.this.private_cluster_config[0].enable_private_nodes &&
      google_container_cluster.this.datapath_provider == "ADVANCED_DATAPATH" &&
      google_container_cluster.this.workload_identity_config[0].workload_pool == "cost-aware-test.svc.id.goog" &&
      google_container_cluster.this.resource_labels["env"] == "nonprod" &&
      google_project_iam_member.nodes.role == "roles/container.defaultNodeServiceAccount" &&
      toset(google_compute_firewall.webhooks.source_ranges) == toset(["172.20.0.0/28"]) &&
      google_container_node_pool.system.node_config[0].labels["team"] == "platform" &&
      try(google_container_node_pool.system.node_config[0].resource_labels["team"], "") == "platform" &&
      google_container_node_pool.system.node_config[0].shielded_instance_config[0].enable_secure_boot
    )
    error_message = "GKE must retain private nodes/API, network policy, workload identity and cost labels."
  }
}

run "reject_world_access" {
  command = plan
  variables {
    operator_access_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.operator_access_cidrs]
}

run "reject_missing_cost_labels" {
  command = plan
  variables {
    cost_tags = { env = "nonprod" }
  }
  expect_failures = [var.cost_tags]
}
