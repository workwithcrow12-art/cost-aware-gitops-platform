# Demo and measurement protocol

This is the evidence for the CV portfolio version. See [portfolio notes](portfolio.md) for contribution boundaries, CV wording and an interview walkthrough. Application code originates from Google Online Boutique; the project work is the surrounding platform, delivery automation, FinOps and verification.

## Run the local checks

Clone the monorepo, then run `python scripts/portfolio_demo.py` from its root with Python 3.11 or later. It runs the offline tests and all three fixture reports, retaining their output in a new directory. See the [five-minute demo](demo.md) and [2026-11-16 evidence](evidence/portfolio-readiness-2026-11-16.md).

For individual checks, run the following from the monorepo root in Bash. The Kubernetes check additionally requires Kustomize.

```bash
for env in dev staging prod preview; do
  kustomize build "gitops-config/apps/boutique/overlays/$env" >/dev/null || exit
done

export PYTHONPATH="$PWD/finops-toolkit/src"
python -m unittest discover -s finops-toolkit/tests -v
python -m finops.cli report --fixtures finops-toolkit/tests/fixtures
python -m finops.cli waste --input finops-toolkit/tests/fixtures/custodian --dry-run
```

| Fixture output | This period | Comparison |
|---|---:|---:|
| OpenCost allocation | $89.47 | $104.00 in the prior week |
| AWS CUR billing | $140.00 | $165.00 in the prior week |
| Cloud Custodian waste estimate | $27.88 per month | 4 candidate resources |

These are synthetic fixtures. OpenCost allocation can overlap with AWS billing, so the report displays the
two sources separately. Waste estimates use fixture rates and represent opportunities for review.
The [generated weekly report](evidence/weekly-report.md) and [waste summary](evidence/waste-report.md) can be read without installing anything. PowerShell commands are in the workspace README.

## Historical local verification on 2026-11-12

The following table is a historical record, not a rerun of the current revision. Counts reflect that earlier version. Checks ran on Windows with cached tools and dependencies. Some test processes required local socket access outside the execution sandbox. Windows Application Control blocked specific compiled test binaries; those results are reported separately below. Hosted GitHub Actions was not run.

| Check | Result |
|---|---|
| Terraform | All 3 roots initialize with backend disabled and validate; 6 mocked plans, formatting and 2 Conftest checks pass |
| Infrastructure bootstrap | Bash syntax and mocked command wiring pass for nonprod, prod and invalid-environment rejection; no real cluster connection |
| GitOps rendering | All 10 Kustomize paths render, including the additional nonprod downscaler RBAC Application |
| Resource schemas | 142 standard resource instances pass kubeconform; the 31 custom resources skipped by kubeconform pass a separate check against CRD schemas from cached, pinned chart renderings |
| Downscaler scope | Rendered nonprod/prod roots and RBAC confirm that only nonprod installs Namespace `get` permission for dev/staging; the chart's service-account helper was checked against the explicit configured name |
| Helm and Kyverno limit | Final reruns are blocked by Windows Application Control. Earlier chart/policy checks are not counted as a fresh verification of the final version; rerun these on Linux |
| GitHub workflow syntax | All 9 workflow files pass actionlint; this does not establish successful hosted workflow execution |
| FinOps | 18 tests and Ruff pass; wheel builds/installs and runs both fixture demos; 4 Custodian policies validate |
| Node.js services | Payment 5 and currency 3 tests pass; currency uses the real service on a local gRPC port |
| Python services | Email 3 and recommendation 6 gRPC tests pass, including the Health Watch regression |
| Checkout | Root package passes successful-order and declined-payment scenarios with local gRPC dependencies |
| Shipping | 10 top-level Go tests pass, including quote subcases |
| Go builds | Frontend, checkout, product catalog and shipping cross-build for Linux/amd64 with CGO disabled |
| Release/smoke tooling | 10 Python tests pass, including failed checkout and blank order/tracking identifiers |
| Java ads service | Offline Gradle assemble succeeds; existing Gradle deprecation warnings remain |
| .NET cart | App and tests compile; Windows Application Control blocks execution of `cartservice.tests.dll` |
| Other Go test limits | Checkout money and frontend validator test binaries are blocked by Windows Application Control. Product catalog uses Unix signals and its tests are cross-compiled for Linux, not executed here |

Docker is unavailable on the verification host, so container builds and current image vulnerability scans were not executed locally. The workflows define those checks for Linux runners. The AWS deployment, registry publishing, controller reconciliation, deployed checkout smoke and measured rollout behavior require a lab run.
The infrastructure uses fixed managed node group counts. CUR and Glue setup use existing AWS billing data.
Karpenter, Goldilocks and Cost Anomaly Detection remain follow-up extensions. A baseline custom Grafana dashboard now exists in `gitops-config/platform/monitoring/dashboards`, and the production Prometheus profile has persistent storage.

## Fixes included in the portfolio version

- Worker launch templates apply cost tags to EC2 and EBS and explicitly retain IMDSv2 with a hop limit of 1. The migration guide explains node group replacement.
- CUR and OpenCost reject missing reporting days instead of treating absent data as zero spending. Tagged FinOps releases depend on the same checks as pull requests.
- Python Health Watch returns the correct gRPC status. Node/Python CI gates and checkout tests cover service behavior and failure paths.
- The downscaler can read the two nonprod Namespace schedules through a narrow ClusterRole. The nonprod bootstrap uses a local manifest path compatible with Kustomize's default load restrictions.
- The storefront smoke command rejects missing confirmation IDs, and runbooks record checkout evidence after deployment and rollback.

The historical review and checks do not establish the current CI result or replace the separate live lab exercise below. Current monorepo promotion and cloud verification limits are recorded in the portfolio notes.

## Reproduce the checks

Run commands from the named component directory after installing its documented dependencies. Use Linux for the complete Go/.NET/container checks where this host was blocked.

| Component directory | Commands |
|---|---|
| `platform-infra` | `make validate`; `conftest verify --policy policies` |
| `gitops-config` | Follow the local validation section of its README and root `.github/workflows/gitops.yml` |
| `finops-toolkit` | `python -m pip install '.[dev,custodian]'`; `make lint test run`; `custodian validate custodian/policies/*.yml` |
| `boutique-app` Node | `npm ci --ignore-scripts` and `npm test` in each of `src/paymentservice` and `src/currencyservice` |
| `boutique-app` Python | Install each service's `requirements.txt`, then run `python -m unittest discover -v` in `src/emailservice` and `src/recommendationservice` |
| `boutique-app` Go | `go test ./...` in frontend, checkoutservice, productcatalogservice and shippingservice |
| `boutique-app` .NET | `dotnet test src/cartservice/tests/cartservice.tests.csproj` |
| `boutique-app` Java | `./gradlew assemble` in `src/adservice` (`gradlew.bat assemble` on Windows) |
| `boutique-app` tooling | `python -m unittest discover -s .github/tests -v` |

The local checkout tests do not prove that Kubernetes service discovery, network policy, admission, secrets and rollout controllers work together. The deployed storefront smoke command in the rebuild runbook tests that separate boundary.

## Run an AWS lab

1. Complete the [AWS prerequisites and evidence checklist](runbooks/aws-lab-evidence.md), then follow the [rebuild runbook](runbooks/khoi-phuc-cluster-tu-git.md) for nonprod. The current zero-cost request has not been verified against an authenticated AWS account; no cloud resources were created.
2. Promote a known-good image set and record the merge and healthy rollout timestamps.
3. In dev, promote a frontend candidate whose HTTP probe fails. Record the analysis status and verify that
   the stable revision still serves traffic. Restore desired state with the [rollback runbook](runbooks/rollback-thu-cong.md).
4. Use matched load and full calendar weeks to compare cost. Record any cluster, pricing or workload changes
   that could affect the comparison.

| Measure | Evidence to capture |
|---|---|
| Deployment frequency | Count healthy production deployments over a fixed period |
| Change lead time | Measure commit to healthy production rollout for the same changes |
| Recovery time | Measure failed candidate detection to restored stable service |
| Cluster rebuild time | Measure Terraform start to the first healthy application sync |
| Nonprod cost | Compare AWS billing for matched weekly windows and use OpenCost to explain allocation |

Record timestamps, revisions and evidence from the run before publishing any measured outcome.
