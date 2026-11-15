# GitOps configuration

Argo CD reconciles Online Boutique and the shared platform from this repository. The manifests ship ten application services and Redis. Dev and staging also run a Locust load generator.

## Bootstrap

The [Vietnamese quick-start](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/blob/main/.github/docs/quick-start.md) connects the infrastructure, GitOps, app and reporting repositories. Bootstrap GKE/AKS labs with `bootstrap-argocd.sh nonprod ../gitops-config YOUR_CONTEXT managed`. This selects `bootstrap/nonprod-managed`, which inherits nonprod and leaves metrics-server to the cloud provider. The default profile retains the EKS add-ons.

Push this repository and the app fork to GitHub before bootstrapping. If you publish under a different owner, update the GitOps URLs and revisions in `bootstrap/`, `applicationsets/`, and `platform/*-app.yaml`, plus the preview PR generator owner. Use public packages for the demo or provide registry pull credentials. For a private GitOps repository, register credentials in Argo CD before the root Application can sync.

Run the Terraform repository's `scripts/bootstrap-argocd.sh nonprod` or `scripts/bootstrap-argocd.sh prod`. It installs Argo CD through Helm and submits `bootstrap/root-app.yaml` with the matching root path.

| Cluster | Root path | Boutique Applications |
|---|---|---|
| Non-production | `bootstrap/nonprod` | `boutique-dev`, `boutique-staging`, and PR previews |
| Production | `bootstrap/prod` | `boutique-prod` |

The roots register AppProjects and an ApplicationSet for pinned Helm add-ons. They also deploy the Kyverno policy and Prometheus rule Applications. The application syncs retry during initial CRD installation.

Use the ClusterIP service to open the storefront in your browser during the dev uptime window. To run a demo outside that window, commit a temporary `downscaler/force-uptime: "true"` annotation in the dev Namespace manifest, then revert it when the demo is finished.

```bash
kubectl -n boutique-dev port-forward svc/frontend 8080:8080
curl --fail http://localhost:8080/_healthz
```

## Release flow

- The base starts with digest-pinned Google Online Boutique `v0.10.7` images and a digest-pinned Redis image.
- The `boutique-app` promotion workflow opens a GitOps pull request for dev. It writes the scanned GHCR manifest digests into the dev overlay's `images` entries, keyed by the original upstream image name.
- Promote the tested image references into the staging and production overlays through GitOps pull requests. Dev and staging sync automatically. Production syncs on operator approval in Argo CD. GitHub branch protection controls reviewer requirements.
- The non-production ApplicationSet requires an open app PR with the `preview` label and a reviewed digest record on this repository's `main` at `apps/boutique/preview-releases/<number>/<head-sha>.json`. The Boutique workflow proposes that record when an operator dispatches a preview. Argo CD removes the preview when the PR closes, the label is removed, or the head changes without a matching record. Preview runs one frontend replica and uses the cart service's in-memory store.

To undo a promotion, revert its GitOps commit and sync the affected Application. A failed frontend analysis aborts the current rollout. Revert the image change to restore the previous desired version in Git.

## Canary signal

The frontend Rollout steps through 25%, 50% and full rollout. With basic canary routing, these weights are targets for the replica ratio. `frontend-canary` selects the candidate ReplicaSet. A Prometheus blackbox probe requests `/` on that service every 15 seconds. At each gate the Rollout pauses, then checks three windows of recent probe samples. A synthetic failure ratio above 1% or a missing series fails the check. The measured ratio describes probe requests and depends on backend services serving the page.

Production includes a frontend HPA and PodDisruptionBudget. For dev and staging, GoKubeDownscaler owns workload replica counts outside the weekday 08:00–20:00 `Asia/Ho_Chi_Minh` window. Argo CD ignores those controller-owned replica fields during reconciliation. Redis uses ephemeral storage in this lab.

The nonprod root also installs `kube-downscaler-rbac`, granting the controller `get` access only to the dev and staging Namespace objects so it can read their schedules. Workload changes remain constrained by the chart's namespaced Roles. The production root installs neither the downscaler nor this additional permission.

## Redis credentials and network boundaries

Dev, staging and prod each require a Secret named `redis-cart` with a `password` key. Redis and cartservice wait for that Secret. Generate a distinct password in each environment and seal it against the controller in the target cluster before syncing the Boutique Application.

```bash
(
  set -euo pipefail
  umask 077
  target=dev
  namespace="boutique-$target"
  temp_dir=$(mktemp -d)
  trap 'rm -f "$temp_dir/password" "$temp_dir/sealed.yaml"; rmdir "$temp_dir"' EXIT
  openssl rand -hex 32 | tr -d '\n' > "$temp_dir/password"
  kubectl -n "$namespace" create secret generic redis-cart \
    --from-file=password="$temp_dir/password" --dry-run=client -o yaml \
  | kubeseal --controller-namespace sealed-secrets --controller-name sealed-secrets \
      --format yaml > "$temp_dir/sealed.yaml"
  mv "$temp_dir/sealed.yaml" "apps/boutique/overlays/$target/redis-cart-sealed.yaml"
)
```

Add `redis-cart-sealed.yaml` to the target overlay's `resources` and commit the encrypted manifest. Follow the coordinated rotation procedure below when replacing an existing password. Preview uses cartservice's in-memory store and has no Redis credential.

The Boutique overlays deny traffic by default and allow the application paths, CoreDNS, and blackbox probes where needed. Only cartservice can connect to Redis. EKS VPC CNI enforces these rules in standard mode, which permits a brief initial window while policy is installed for new Pods. Boutique Pods disable default service account token mounting.

GitOps validation scans each deployed Redis digest with Trivy and blocks HIGH or CRITICAL vulnerabilities and end-of-life base operating systems. The base uses Redis 8.10.3 on Alpine 3.23, pinned to its verified manifest index.

## Cost and reporting

- Kyverno enforces `team` and `env` labels, SHA-256 image digests, and CPU and memory requests and limits in `boutique-*` namespaces.
- OpenCost queries the in-cluster Prometheus. Use `kubectl -n opencost port-forward svc/opencost 9003:9003` and request `http://localhost:9003/allocation/compute?window=1h&aggregate=namespace,label:team,label:env` after the cluster has collected samples.
- `platform/finops-reporter` is an opt-in Kustomize app. After publishing the configured `finops-toolkit:v0.9` image, add an Argo CD Application pointing to this path with the `platform` project and destination namespace `finops`. The Monday CronJob writes its report to logs. For AWS billing, the Terraform cost-reporting module supplies `reporter_environment` and `reporter_role_arn`; copy the environment into the CronJob and annotate its ServiceAccount with `eks.amazonaws.com/role-arn`. Configure Slack or Telegram credentials in an optional sealed `finops-reporter` Secret.
- Grafana, Prometheus and OpenCost ship as Helm add-ons. Prometheus evaluates probe, hourly node-cost and reporter-job alerts. The production profile adds persistent storage; external notification routing needs a sealed destination Secret as described below.

Use the Sealed Secrets controller in namespace `sealed-secrets`, service name `sealed-secrets`, when encrypting secrets. Encrypt separately for each target cluster and add the resulting manifest to the overlay's resources.

## Local validation

```bash
set -euo pipefail
for path in apps/boutique/overlays/{dev,staging,prod,preview} bootstrap/{nonprod,nonprod-managed,prod}; do
  kubectl kustomize "$path" | kubeconform -strict -ignore-missing-schemas -summary -kubernetes-version 1.35.0
done
kyverno test platform/kyverno/tests
```

The GitHub workflow also renders the policies, Prometheus rules, reporter and downscaler RBAC. Kyverno tests include partial limits, init containers, Deployment autogeneration and namespace exclusions. Schema validation skips custom resources without a configured schema. A cluster sync verifies controller reconciliation.

Grafana loads the baseline **FinOps allocation and availability** dashboard from
`platform/monitoring/dashboards`. It shows node cost, CPU/memory allocation by
namespace and frontend candidate availability using existing Prometheus metrics.
Node costs and workload allocations overlap; do not add them together. Waste
candidates remain in the CLI report rather than being represented as live metrics.

## Monitoring storage and notifications

The production bootstrap adds `platform/storage` and loads `values-prod.yaml`
after the shared Helm values. Prometheus requests an encrypted 20 GiB gp3 volume
and retains up to 30 days or 18 GB of samples. Apply the production Terraform
configuration first to install the EBS CSI driver and its IRSA role. The volume
survives Pod replacement, but is not a backup or a multi-zone replica. The
StorageClass uses `Retain`: deleting a PVC or cluster does not delete the disk;
review retained disks explicitly during teardown to stop ongoing storage charges.
Nonprod remains ephemeral. The production storage profile is AWS-specific.

Alertmanager is enabled. External delivery requires a destination you control:

1. Seal a Secret named `alertmanager-slack` in namespace `monitoring`, with key
   `webhook-url`, using the target cluster's Sealed Secrets controller. Keep its
   plaintext input in a protected temporary file, not a command argument.
2. Save the encrypted manifest as
   `platform/monitoring/notifications/alertmanager-slack-sealed.yaml` and add it
   to that directory's `kustomization.yaml` resources.
3. Enable `monitoring-notifications-app.yaml` in `platform/kustomization.yaml`.
   Its AlertmanagerConfig routes warning/critical alerts, including cluster cost,
   canary availability and failed FinOps reporter jobs, to the sealed Slack URL.
4. Sync, inspect Alertmanager's configuration/status, and verify delivery with a
   controlled test alert. Until a receiver is configured, alerts are visible
   locally but no external message is sent. Remove acknowledged failed Job
   objects after investigation to clear their job-failure alerts.

For direct reporter failure notices, add `NOTIFY_FAILURES=true` and `NOTIFIER`
plus the destination credentials to the optional sealed `finops-reporter` Secret.
Publish the updated toolkit image and update the CronJob image before using this.

## Workload security and credential rotation

All Boutique overlays apply the `restricted` component: UID/GID 1000, nonroot,
RuntimeDefault seccomp, no privilege escalation, and all capabilities dropped.
Redis's data volume uses fsGroup 1000. Kyverno enforces the restricted standard
in Boutique namespaces, including init containers and future sidecars. CI checks
both rejection fixtures and the rendered workload templates. Verify new images
under these permissions before promotion; admission tests cannot establish image
runtime compatibility.

Rotate Redis credentials during a maintenance window using the sealing procedure
above. Commit and sync the new encrypted Secret, and verify that the controller
has updated the underlying Kubernetes Secret. Then update
`spec.template.metadata.annotations` with a new `credentials-revision` value on
**both** Redis and cartservice in a second GitOps change, so Secret environment
variables are reloaded. Sync, verify Redis readiness and run the checkout smoke test.
The lab's ephemeral Redis loses carts on restart, and changing its single password
can briefly interrupt requests. A blind rotation CronJob would hide those effects.
Sealing-key renewal is automatic; it does not rotate the Redis password.
