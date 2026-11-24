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
v* tag → require successful validation of current main → rebuild, scan and publish → release
deployment → review published digest records → GitOps PR → Argo CD sync
```

Active workflows are at the monorepo root: `.github/workflows/services.yml`, `images.yml`, `ci.yml` and `release.yml`. Nested workflows are standalone examples and do not run here. Automatic dev promotion and dispatched preview publication have not been ported to root workflows. A push to `main` validates images with `publish: false`.

The matrix builds all 11 images from one revision, including the optional load generator. Trivy scans the local Docker image before publication and blocks HIGH or CRITICAL vulnerabilities. The publication job retains a manifest digest record for each service. The GitOps base remains on pinned upstream images until a deployment PR changes it; SHA tags alone do not update a cluster.

## Connect GitHub and GitOps

1. Protect `main` in the monorepo and require review of workflow, bootstrap and deployment changes. Active workflows do not need a cross-repository `GITOPS_TOKEN` or a `gitops-promotion` environment; those settings belong only to the nested examples.
2. Give clusters pull access to GHCR packages. The lab assumes public packages; newly published packages may need their visibility changed, or private-registry credentials configured.
3. After successful `v0.9` publication, download the `scanned-image-*` artifacts before their three-day retention expires. Check that all records identify the intended revision. From the monorepo root, run `python boutique-app/.github/scripts/scanned-images.py --help` for helper inputs. It validates records and prints image replacements; it does not open a PR.
4. Propose reviewed digests in `gitops-config/apps/boutique/overlays/dev/kustomization.yaml`, then promote the tested references to staging and production in separate PRs. Preview manifests are configured, but the operator must prepare and review the matching release record. No active workflow generates it; see the GitOps README for record paths and cleanup conditions.

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
