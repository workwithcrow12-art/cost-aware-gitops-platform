#!/usr/bin/env bash
set -euo pipefail

environment=${1:-}
if [[ "$environment" == aks || "$environment" == gke ]]; then
  default_profile=managed
else
  default_profile=standard
fi
profile=${4:-$default_profile}

case "$profile:$environment" in
  standard:nonprod|standard:prod|managed:nonprod|managed:aks|managed:gke) ;;
  *) printf 'Usage: %s nonprod|prod|aks|gke [gitops-checkout] [kube-context] [standard|managed (nonprod/aks/gke only)]\n' "$0" >&2; exit 2 ;;
esac

if [[ "$environment" == prod ]]; then
  root_path="gitops-config/bootstrap/prod"
elif [[ "$profile" == managed ]]; then
  root_path="gitops-config/bootstrap/nonprod-managed"
else
  root_path="gitops-config/bootstrap/nonprod"
fi

scripts_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
gitops_dir=${2:-"$scripts_dir/../../gitops-config"}
root_app="$gitops_dir/bootstrap/root-app.yaml"
bootstrap_project="$gitops_dir/bootstrap/projects/bootstrap.yaml"
argo_values="$gitops_dir/platform/argocd/values.yaml"
if [[ ! -f "$root_app" || ! -f "$bootstrap_project" || ! -f "$argo_values" ]]; then
  printf 'GitOps checkout is missing the root app, bootstrap project or Argo CD values: %s\n' "$gitops_dir" >&2
  exit 2
fi

context=${3:-}
if [[ -z "$context" ]]; then
  context=$(bash "$scripts_dir/get-kubeconfig.sh" "$environment")
fi
helm upgrade --install argocd argo-cd \
  --repo https://argoproj.github.io/argo-helm --version 8.5.8 \
  --kube-context "$context" --namespace argocd --create-namespace \
  --values "$argo_values" --wait --timeout 10m

kubectl --context "$context" --namespace argocd apply -f "$bootstrap_project"
kubectl patch --local --type merge -f "$root_app" \
  --patch "{\"spec\":{\"source\":{\"path\":\"$root_path\"}}}" -o yaml \
  | kubectl --context "$context" --namespace argocd apply -f -
