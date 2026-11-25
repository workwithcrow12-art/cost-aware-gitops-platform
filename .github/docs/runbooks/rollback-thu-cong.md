# Manual GitOps Application Rollback

An Argo Rollouts canary abort keeps the prior stable ReplicaSet serving traffic in-cluster, but **Git still points to the failing candidate commit** until you revert desired state in `gitops-config`. Use this runbook to restore a known-good application revision cleanly.

## Procedure

1. **Identify the target overlay and bad commit:** Confirm the affected environment (`dev`, `staging`, or `prod`), the last healthy `ghcr.io/workwithcrow12-art/<service>@sha256:...` digests, and the promotion PR/commit (for example, a commit from `promote-images.yml` or manual overlay change) that introduced the regression.
2. **Open a Git revert PR:** From a new branch off `main`, revert the offending GitOps commit without rewriting history:

   ```bash
   git checkout -b fix/rollback-boutique main
   git revert <bad-promotion-commit-sha>
   ```

   Open a Pull Request against `main` and wait for `Release validation` (`ci.yml` / `gitops.yml`) to pass.
3. **Merge and reconcile:** Merge the revert PR. `dev` and `staging` reconcile automatically in Argo CD; for `prod`, approve and trigger a manual sync in Argo CD (`boutique-prod`).
4. **Verify Rollout and pod health:** Confirm the Rollout returns to `Healthy` and candidate failure pods terminate:

   ```bash
   kubectl -n <namespace> get rollouts,analysisruns,pods
   ```

5. **Run post-rollback checkout verification:** Port-forward `svc/frontend` (`8080:8080`) and run the storefront checkout smoke check (using `python scripts/cloud_lab_runner.py --env <nonprod|prod> --execute-stage smoke` or `python boutique-app/.github/scripts/smoke-checkout.py --base-url http://localhost:8080`). Save the exit status, restored `@sha256` digests, and UTC recovery timestamp using only the lab's mock payment and email handlers.
