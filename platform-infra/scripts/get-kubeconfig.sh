#!/usr/bin/env bash
set -euo pipefail

environment=${1:-}
case "$environment" in
  nonprod|prod|aks|gke) ;;
  *) printf 'Usage: %s nonprod|prod|aks|gke\n' "$0" >&2; exit 2 ;;
esac

infra_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root="$infra_dir/envs/$environment"

case "$environment" in
  nonprod|prod)
    cluster_name=$(terraform -chdir="$root" output -raw cluster_name)
    cluster_arn=$(terraform -chdir="$root" output -raw cluster_arn)
    region=$(terraform -chdir="$root" output -raw aws_region)
    aws_options=()
    if [[ -n ${EKS_OPERATOR_PROFILE:-} ]]; then
      aws_options+=(--profile "$EKS_OPERATOR_PROFILE")
    fi
    aws "${aws_options[@]}" eks update-kubeconfig --name "$cluster_name" --region "$region" --alias "$cluster_arn" >&2
    printf '%s\n' "$cluster_arn"
    ;;
  aks)
    rg_name=$(terraform -chdir="$root" output -raw resource_group_name)
    cluster_name=$(terraform -chdir="$root" output -raw cluster_name)
    kube_context=$(terraform -chdir="$root" output -raw kube_context)
    az aks get-credentials --resource-group "$rg_name" --name "$cluster_name" --overwrite-existing >&2
    printf '%s\n' "$kube_context"
    ;;
  gke)
    cluster_name=$(terraform -chdir="$root" output -raw cluster_name)
    kube_context=$(terraform -chdir="$root" output -raw kube_context)
    # Extract --zone and --project from the get_credentials_command output
    creds_cmd=$(terraform -chdir="$root" output -raw get_credentials_command)
    zone=$(awk '{for(i=1;i<=NF;i++) if($i=="--zone") print $(i+1)}' <<< "$creds_cmd")
    project=$(awk '{for(i=1;i<=NF;i++) if($i=="--project") print $(i+1)}' <<< "$creds_cmd")
    gcloud container clusters get-credentials "$cluster_name" --zone "$zone" --project "$project" --internal-ip >&2
    printf '%s\n' "$kube_context"
    ;;
esac
