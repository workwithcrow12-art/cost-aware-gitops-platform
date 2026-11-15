# boutique-app

Application source for the [Cost-aware GitOps Platform](https://github.com/cost-aware-gitops-platform),
and the CI that builds, scans and ships it.

> This repository is a fork of
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

## Pipeline

```text
pull request → Go, .NET, Node.js and Python tests → container builds → Trivy scan
main push    → same checks → publish scanned images → open or refresh the GitOps dev PR
preview      → dispatch on protected main → build the approved PR head → open a GitOps preview PR
```

The matrix builds a complete set of 11 images from one revision, including the optional load generator.
Trivy scans the local Docker image before publication and blocks on HIGH or CRITICAL vulnerabilities.
Promotion takes the manifest digest from that same push and validates all 11 records from the current run.
GitOps deploys those digests. SHA tags in GHCR identify the source revision for browsing.

## Connect GitHub and GitOps

1. Protect `main` in both repositories and require review of workflow and bootstrap changes. In this repository,
   create the GitHub Actions environment `gitops-promotion` and restrict deployments to `main`. Store
   `GITOPS_TOKEN` only as an environment secret. Grant the token Contents and Pull requests write access only
   to the config repository, with no bypass of its branch rules. Remove any old repository-level copy of
   this secret. Set `GITOPS_REPOSITORY` if it differs from `<owner>/gitops-config`.
2. Give the clusters pull access to the GHCR packages. The lab manifests assume public packages, which GitHub
   can create with private visibility on the first push. Use public packages only for code intended to be public.
3. After the regular PR checks pass, add the `preview` label to a reviewed same-repository PR into `main`.
   Dispatch **Build Online Boutique**
   from protected `main`, providing the PR number and its full head SHA. Review and merge the resulting GitOps
   PR to allow that exact revision to run. Closing the app PR, removing its label or changing its head triggers
   cleanup when Argo CD next polls. Dispatch again to preview a new revision.
4. Review and merge the dev PR. For staging and production, propose the same tested digests in each environment
   overlay through separate GitOps PRs.

## Local development

Run `go test ./...` in the frontend, checkoutservice, productcatalogservice or shippingservice directory.
The product catalog service uses Unix signals, so run its test suite on Linux.
Run `dotnet test src/cartservice/tests/cartservice.tests.csproj` from this repository to test the cart service.
Run `npm ci --ignore-scripts && npm test` in `src/paymentservice` and `src/currencyservice` with Node.js 24. Payment tests cover accepted, invalid, expired and unsupported cards; currency tests start the actual gRPC server on a local port.
With Python 3.14 and a virtual environment, run `python -m pip install -r requirements.txt` followed by `python -m unittest discover -v` in `src/emailservice` and `src/recommendationservice`. These tests use loopback gRPC servers to check health responses, mock email confirmation and recommendation filtering and limits; they need local socket access.
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
