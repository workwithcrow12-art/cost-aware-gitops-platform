#!/usr/bin/env bash
set -euo pipefail

environment=${1:-}
case "$environment" in
  nonprod|prod) ;;
  *) printf 'Usage: %s nonprod|prod\n' "$0" >&2; exit 2 ;;
esac

infra_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
root="$infra_dir/envs/$environment"
cluster_name=$(terraform -chdir="$root" output -raw cluster_name)
cluster_arn=$(terraform -chdir="$root" output -raw cluster_arn)
region=$(terraform -chdir="$root" output -raw aws_region)

aws_options=()
if [[ -n ${EKS_OPERATOR_PROFILE:-} ]]; then
  aws_options+=(--profile "$EKS_OPERATOR_PROFILE")
fi
aws "${aws_options[@]}" eks update-kubeconfig --name "$cluster_name" --region "$region" --alias "$cluster_arn" >&2
printf '%s\n' "$cluster_arn"
