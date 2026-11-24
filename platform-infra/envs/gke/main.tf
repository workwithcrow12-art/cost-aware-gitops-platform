provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "apis" {
  for_each           = toset(["compute.googleapis.com", "container.googleapis.com", "iam.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_network" "this" {
  name                    = var.name
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "this" {
  name                     = var.name
  region                   = var.region
  network                  = google_compute_network.this.id
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_5_SEC"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.44.0.0/16"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.45.0.0/20"
  }
}

resource "google_compute_router" "this" {
  name    = var.name
  region  = var.region
  network = google_compute_network.this.id
}

resource "google_compute_router_nat" "this" {
  name                               = var.name
  router                             = google_compute_router.this.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

resource "google_service_account" "nodes" {
  account_id   = "${var.name}-nodes"
  display_name = "GKE lab nodes"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "nodes" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

# Private GKE control planes need an explicit path to Kyverno's admission webhook.
resource "google_compute_firewall" "webhooks" {
  name                    = "${var.name}-webhooks"
  network                 = google_compute_network.this.id
  source_ranges           = ["172.20.0.0/28"]
  target_service_accounts = [google_service_account.nodes.email]
  allow {
    protocol = "tcp"
    ports    = ["9443"]
  }
}

resource "google_project_iam_member" "operator" {
  project = var.project_id
  role    = "roles/container.admin"
  member  = var.operator_member
}

resource "google_container_cluster" "this" {
  name                     = var.name
  location                 = var.zone
  network                  = google_compute_network.this.id
  subnetwork               = google_compute_subnetwork.this.id
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = var.deletion_protection
  resource_labels          = var.cost_tags
  datapath_provider        = "ADVANCED_DATAPATH"

  release_channel {
    channel = "REGULAR"
  }
  node_config {
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    resource_labels = var.cost_tags
  }
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true
    master_ipv4_cidr_block  = "172.20.0.0/28"
    master_global_access_config {
      enabled = true
    }
  }
  master_authorized_networks_config {
    private_endpoint_enforcement_enabled = true
    dynamic "cidr_blocks" {
      for_each = var.operator_access_cidrs
      content {
        cidr_block = cidr_blocks.value
      }
    }
  }
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  depends_on = [google_project_iam_member.nodes, google_compute_router_nat.this, google_compute_firewall.webhooks]
}

resource "google_container_node_pool" "system" {
  name       = "system"
  cluster    = google_container_cluster.this.name
  location   = var.zone
  node_count = var.node_count
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  node_config {
    machine_type    = "e2-standard-4"
    disk_size_gb    = 30
    disk_type       = "pd-balanced"
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    labels          = var.cost_tags
    resource_labels = var.cost_tags
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }
}
