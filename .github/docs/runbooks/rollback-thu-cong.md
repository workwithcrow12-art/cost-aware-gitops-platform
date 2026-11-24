# Restore the previous app revision

1. Confirm the environment, the last healthy revision and the GitOps commit that changed the image digests.
2. From a branch based on the monorepo's `main`, run `git revert <bad-promotion-commit>` and open a PR.
3. Merge the revert. Sync manually if the target Application requires it.
4. Inspect the rollout with `kubectl -n <namespace> get rollouts,analysisruns,pods` and verify the frontend responds.
5. Port-forward the restored frontend service and run `python .github/scripts/smoke-checkout.py --base-url http://localhost:8080` from `boutique-app`. Save the exit status, restored image digests and timestamps with the exercise record. Use only the lab's mock payment and email services.

A canary abort can keep the stable revision serving while Git still points to the failing candidate.
The revert restores the desired state.
