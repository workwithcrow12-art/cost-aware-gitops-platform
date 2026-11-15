# Canary rollback exercise

This is the drill plan. Use the dev overlay and record the actual outcome during a lab run.

1. Save the stable image revision and confirm that the frontend is healthy.
2. In the dev frontend Pod template, change `PRODUCT_CATALOG_SERVICE_ADDR` to `missing-catalog:3550` through GitOps.
   This drill targets the candidate's storefront probe at `/`. The readiness probe at `/_healthz` uses a separate handler.
   Record when the rollout starts and when the analysis fails.
3. Capture the rollout, AnalysisRun and stable frontend health. Check whether traffic continued reaching the stable pods.
4. Revert the GitOps change, confirm reconciliation and record recovery time.

In the exercise record, include the fault, the probe result, the user-visible impact and the next change to test.
