# Exercise Plan: Frontend Canary Auto-Rollback Drill

This postmortem template and fault-injection drill plan exercises Argo Rollouts progressive delivery and automatic analysis abort on the `dev` overlay (`boutique-dev`). Never run fault-injection drills against `prod`. Record actual UTC timestamps, commit SHAs, and logs in `.scratch/aws-lab-<timestamp>` before claiming measured recovery metrics.

## Drill Procedure

1. **Record the healthy baseline:**
   - Confirm `boutique-dev` is within its active uptime window (`08:00–20:00` weekdays `Asia/Ho_Chi_Minh`, or temporarily apply `downscaler/force-uptime: "true"` on the `boutique-dev` Namespace).
   - Record the active `ghcr.io/workwithcrow12-art/frontend@sha256:...` digest, verify `kubectl -n boutique-dev get rollout frontend` is `Healthy`, and pass `python boutique-app/.github/scripts/smoke-checkout.py --base-url http://localhost:8080`.
2. **Inject a candidate dependency fault via GitOps:**
   - Open and merge a PR updating the `dev` frontend Pod template environment variable `PRODUCT_CATALOG_SERVICE_ADDR` to `missing-catalog:3550` (alongside a pod-template change so Argo Rollouts creates a new canary ReplicaSet).
   - Rationale: the container's `/_healthz` readiness handler still responds, while the Prometheus blackbox probe targeting `/` on `frontend-canary` fails (`> 1%` error rate across consecutive 15-second probe windows) because the storefront home page cannot query `productcatalogservice`.
3. **Observe candidate analysis failure and stable-pod isolation:**
   - Record the UTC timestamp when Argo CD syncs the candidate commit and when the `AnalysisRun` transitions to `Failed` / Rollout transitions to `Degraded` (aborted).
   - Capture `kubectl -n boutique-dev get rollouts,analysisruns,pods` and verify that candidate traffic weight drops to `0` while stable ReplicaSet pods continue serving requests cleanly.
4. **Restore Git desired state:**
   - Because an Argo Rollouts abort halts progression in the cluster without rewriting Git history, follow the [manual rollback runbook](../runbooks/rollback-thu-cong.md) (`git revert <fault-commit>`) so `gitops-config` matches the healthy desired state again.
   - Confirm Argo CD reconciles back to `Healthy` and rerun `smoke-checkout.py` to record total Git desired-state recovery time separately from user-facing stable-service availability.

## Post-Exercise Record Checklist

- Fault commit SHA, revert commit SHA, and pinned `frontend` image digest
- `AnalysisRun` failure metric output and probe window timestamps
- User-visible impact on the stable `frontend` Service during candidate failure
- Follow-up improvements (for example, synthetic checkout probes vs `/` availability probes, or traffic-router integration beyond replica-ratio weighting)
