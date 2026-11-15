#!/usr/bin/env bash
set -euo pipefail

environment=${1:-}
profile=${4:-standard}
case "$profile:$environment" in
  standard:nonprod|standard:prod|managed:nonprod) ;;
  *) printf 'Usage: %s nonprod|prod [gitops-checkout] [kube-context] [standard|managed (nonprod only)]\n' "$0" >&2; exit 2 ;;
esac
root_path="gitops-config/bootstrap/$environment"
if [[ "$profile" == managed ]]; then
  root_path="$root_path-managed"
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
