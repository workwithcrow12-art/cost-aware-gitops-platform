# boutique-app

Application source for the [Cost-aware GitOps Platform](https://github.com/workwithcrow12-art/cost-aware-gitops-platform),
and the CI that builds, scans and ships it.

> The application source derives from
> [GoogleCloudPlatform/microservices-demo](https://github.com/GoogleCloudPlatform/microservices-demo) (Apache 2.0).
> The project adds CI, container scanning and GitOps promotion around the upstream service code.
> A checkout error-status call also has a one-line compatibility fix for Go vet.
> Python health Watch calls return the gRPC UNIMPLEMENTED status expected by clients.

## Services

| Service | Language | Description |
|---|---|---|
| frontend | Go | Web UI, deployed as an Argo Rollout canary |
| cartservice | C# | Shopping cart, backed by Redis |
| productcatalogservice | Go | Product list and search |
| currencyservice | Node.js | Currency conversion |
| paymentservice | Node.js | Mock payment processing |
| shippingservice | Go | Shipping cost and mock shipment |
| emailservice | Python | Mock order confirmation email |
| checkoutservice | Go | Orchestrates the order |
| recommendationservice | Python | Product recommendations |
| adservice | Java | Contextual ads |
| loadgenerator | Python (Locust) | Optional simulated traffic in dev and staging |
| shoppingassistantservice | Python (Flask / Gemini / AlloyDB) | Optional GCP-only RAG assistant (excluded from base deployment and GHCR image matrix; unit-tested in `services.yml`) |

## Pipeline

```text
pull request / main push → service tests → container builds → HIGH/CRITICAL scan gate
v* tag → require successful validation of current main → rebuild, scan and publish → release + promote-images PR
deployment → review GitOps digest promotion PR → merge → Argo CD sync
```

Active application workflows live at the monorepo root: `.github/workflows/services.yml`, `images.yml`, `ci.yml`, `release.yml`, and `promote-images.yml`. Nested workflows under `boutique-app/` are standalone examples and do not run here. A push to `main` validates images with `publish: false`.

The matrix builds all 11 images from one revision, including the optional load generator. Trivy scans the local Docker image before publication and blocks HIGH or CRITICAL vulnerabilities. The publication job retains a manifest digest record (`scanned-image-<service>`) for each service, while `release.yml` also publishes and records `scanned-image-finops-toolkit`. `gitops-config/apps/boutique/base` retains pinned upstream image names so Kustomize `images:` overrides in `overlays/{dev,staging,prod,preview}` map cleanly to immutable `ghcr.io/workwithcrow12-art/<service>@sha256:...` (`v0.9`) digests; SHA tags alone never mutate a cluster.

## Connect GitHub and GitOps

1. Protect `main` in the monorepo with `Release validation` status checks and review workflow, bootstrap, and deployment changes. Active monorepo workflows use scoped `GITHUB_TOKEN` permissions (`contents: write`, `pull-requests: write`, `actions: read` in `promote-images.yml`) and do not require a cross-repository `GITOPS_TOKEN` or a `gitops-promotion` environment.
2. Give clusters pull access to GHCR packages. The lab uses public packages; newly published packages may need their visibility set to public, or private-registry pull credentials configured.
3. After `release.yml` finishes publishing a `v*` tag, its `promote` job automatically invokes `.github/workflows/promote-images.yml` to download the `scanned-image-*` artifacts, run `boutique-app/.github/scripts/scanned-images.py --apply-gitops gitops-config --finops-record ...`, validate overlays and `platform/finops-reporter` with `kubectl kustomize`, and open a GitOps promotion PR. You can also trigger `promote-images.yml` via `workflow_dispatch` for `all`, `dev`, `staging`, `prod`, or `preview` before the three-day artifact retention expires.
4. From the monorepo root, `python boutique-app/.github/scripts/scanned-images.py <records> <owner> <revision> <dev|staging|prod|preview>` prints backwards-compatible `{"images": [...]}` JSON replacements (`dev` and `staging` include `loadgenerator`; `prod` and `preview` omit it), and `--apply-gitops gitops-config` (with optional `--finops-record`) updates the overlay `kustomization.yaml` `images:` block and `gitops-config/platform/finops-reporter/cronjob.yaml` deterministically in place. Preview deployments still require an open PR labeled `preview` and a reviewed record under `gitops-config/apps/boutique/preview-releases/<number>/<head-sha>.json`; see the GitOps README for record paths and cleanup conditions.

## Local development

Run `go vet ./... && go test -race ./...` in the frontend, checkoutservice, productcatalogservice or shippingservice directory.
The product catalog service uses Unix signals, so run its test suite on Linux.
Run `./gradlew test --no-daemon` in `src/adservice` with Java 21 to test the contextual ad gRPC service.
Run `dotnet test src/cartservice/tests/cartservice.tests.csproj` from this repository to test the cart service.
Run `npm ci --ignore-scripts && npm test` in `src/paymentservice` and `src/currencyservice` with Node.js 24. Payment tests cover accepted, invalid, expired and unsupported cards; currency tests start the actual gRPC server on a local port.
With Python 3.14 and a virtual environment, run `python -m pip install -r requirements.txt` followed by `python -m unittest discover -v` in `src/emailservice`, `src/recommendationservice`, and `src/loadgenerator` (and `python -m unittest discover -v` with `flask` installed in `src/shoppingassistantservice`). The gRPC service tests use loopback servers and need local socket access.
The checkout Go suite exercises order totals, cart clearing and a declined payment through in-memory gRPC dependencies. It does not require AWS or a cluster.
Run `python -m unittest discover -s .github/tests` to test the release record validation and the HTTP smoke command against a local test server. The HTTP and currency checks require local socket access.
Build an individual image with `docker build -t boutique-frontend src/frontend`. The cart service's build context
is `src/cartservice/src`. Deploy the platform manifests from
[gitops-config](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/tree/main/gitops-config).

## Storefront smoke test

After deploying nonprod and configuring its Redis secret, keep `kubectl -n boutique-dev port-forward svc/frontend 8080:8080` running in a separate terminal. During the dev uptime window, run from this repository:

```bash
python .github/scripts/smoke-checkout.py --base-url http://localhost:8080
```

The command uses a fresh session, adds one catalog product, submits the demo Visa card, checks the order confirmation and verifies that the cart is empty. It places one synthetic order using the lab's mock payment and email services. A failed request or missing confirmation exits nonzero. Run it after promotion and after rollback, recording the deployed image revision with the result. The local test suite validates the smoke command; a successful run against the deployed storefront is separate end-to-end evidence.

## License

Apache 2.0. See [LICENSE](LICENSE).
