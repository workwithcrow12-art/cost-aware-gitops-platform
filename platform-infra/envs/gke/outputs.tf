output "cluster_name" {
  value = google_container_cluster.this.name
}

output "kube_context" {
  value = "gke_${var.project_id}_${var.zone}_${var.name}"
}

output "get_credentials_command" {
  value = "gcloud container clusters get-credentials ${var.name} --project ${var.project_id} --zone ${var.zone} --internal-ip"
}
