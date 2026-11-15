# finops-toolkit

Cost reporting and waste detection for the [Cost-aware GitOps Platform](https://github.com/cost-aware-gitops-platform).
The report can run weekly as a Kubernetes CronJob and optionally send results to Telegram or Slack.

## What it does

| Command | Description |
|---|---|
| `finops report` | Compares two complete seven-day UTC windows by environment and team, using OpenCost and optional AWS CUR (Athena) |
| `finops waste` | Summary of Cloud Custodian findings with an estimated monthly cost: unattached EBS volumes, unused Elastic IPs, old snapshots, idle load balancers |
| `finops cloud-report` | Compares normalized FOCUS CSV billed costs across providers, environments and teams, with separate totals per currency |

## Offline demo

With Python 3.11 or newer, run from this repository root. The demo reads synthetic fixtures locally and needs no credentials, Python dependencies, or cluster.

```bash
PYTHONPATH=src python -m finops.cli report --fixtures tests/fixtures
PYTHONPATH=src python -m finops.cli waste --input tests/fixtures/custodian --dry-run
```

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m finops.cli report --fixtures tests/fixtures
python -m finops.cli waste --input tests/fixtures/custodian --dry-run
```

The synthetic fixture shows $89.47 vs $104.00 in Kubernetes allocations, $140.00 vs $165.00 in AWS CUR costs, and four waste candidates with an estimated $27.88 per month.

## Multi-cloud billing report

```bash
PYTHONPATH=src python -m finops.cli cloud-report --input tests/fixtures/focus_sample.csv --as-of 2026-01-19
```

The synthetic FOCUS fixture covers AWS, Google Cloud and Microsoft Azure, totaling 43.75 USD in each week. For real data, combine billing exports into a single CSV with one header and the following [FOCUS 1.0/1.1](https://focus.finops.org/wp-content/uploads/2024/11/FOCUS-spec-v1_1.pdf) columns. This command imports a documented subset; it does not certify full FOCUS conformance or download cloud bills.

| Column | Required value |
| --- | --- |
| `ProviderName` | Non-empty provider name; keep naming consistent across exports |
| `BillingCurrency` | Three uppercase letters, e.g. `USD`, `EUR`; currencies stay separate |
| `BilledCost` | Finite decimal; zero and negative credits are retained |
| `ChargePeriodStart`, `ChargePeriodEnd` | UTC timestamps with `Z` or `+00:00`, start inclusive/end exclusive, within a single UTC day |
| `Tags` | JSON object with string values; `env` and `team` drive grouping; blank/JSON null or absent labels become `unallocated` |

Extra columns such as `ServiceName` are allowed and ignored. UTF-8 BOM is accepted. Use hourly/daily rows; normalize monthly purchases or intervals crossing UTC midnight before import, with an explicit allocation method in the export process. The command rejects these intervals rather than attributing the entire charge to the start day. Native provider formats and FOCUS versions that omit/rename `ProviderName` need conversion to this contract first.

`--as-of` is the exclusive end date, defaulting to today UTC. Each provider present in the selected two weeks needs at least one charge row on every one of the 14 completed UTC days. Missing data aborts before printing a report. Daily presence does not prove complete charges, and the reader cannot detect a provider omitted entirely or duplicate charges: reconcile the source exports. Do not append the same export twice or add these billing totals to overlapping OpenCost allocations. Currencies stay separate by default.

To append a USD comparison, supply `--usd-rates rates.json` with a JSON object such
as `{"EUR": 1.10, "GBP": 1.25}`. Each number means USD per one unit of the source
currency; USD is always 1. Every encountered non-USD currency must have a positive,
finite numeric rate. Duplicate keys, missing rates and an altered USD rate stop
the report before any output. The original currency sections remain available.
Record the rate source and valuation date with your report: the same supplied
table applies to both weeks, so this is a constant-rate comparison, not an
invoice settlement calculation. The CLI never downloads exchange rates.

The command always prints locally and never sends notifications. The existing `report` and `waste` commands retain their behavior. See the [Vietnamese quick-start](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/blob/main/.github/docs/quick-start.md) for the cross-repository setup.

## Live report

```bash
python -m pip install .       # Use '.[aws]' when querying Athena.
export OPENCOST_URL=http://localhost:9003
finops report --dry-run
```

Point `OPENCOST_URL` at an instance with 14 completed UTC days of metrics. The client requests daily allocation sets and rejects a missing or empty day before printing or notifying a report. Zero-cost allocations remain valid. In a lab, port-forward the OpenCost deployment with `kubectl -n opencost port-forward deployment/opencost 9003`. `--dry-run` skips notifications while still collecting configured live data. Omit `--dry-run` after configuring a notification destination.

Export the environment variables below or populate `.env` from `.env.example` and load it in your shell before running the CLI.

| Variable | Description |
|---|---|
| `OPENCOST_URL` | OpenCost API, e.g. `http://opencost.opencost.svc:9003` |
| `ATHENA_TABLE` | Legacy CUR table name. Set to enable Athena or leave empty to run OpenCost only. |
| `AWS_REGION` | Region of the Athena workgroup and Glue catalog |
| `ATHENA_DATABASE` | Glue database holding the CUR table |
| `ATHENA_WORKGROUP` | Athena workgroup |
| `ATHENA_OUTPUT_S3` | S3 location for Athena query results |
| `NOTIFIER` | `telegram` or `slack`. Leave empty to print to stdout. |
| `NOTIFY_FAILURES` | Set `true` to send a generic failure notice when live `report` or `waste` generation fails. Defaults to off; fixtures and `--dry-run` never notify. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram destination |
| `SLACK_WEBHOOK_URL` | Slack destination |

The OpenCost report uses workload labels `env` and `team`. It reports idle costs and unlabeled allocations separately. For Athena, configure the legacy CUR with Athena integration, activate the `env` and `team` cost allocation tags, and allow the data to arrive in Glue. The packaged query assumes USD-denominated CUR unblended costs. The AWS and Kubernetes totals are shown separately because the sources may overlap. Compare periods only after checking data freshness and coverage. [OpenCost Allocation API](https://opencost.io/docs/integrations/api/) · [AWS CUR Athena guide](https://docs.aws.amazon.com/cur/latest/userguide/cur-query-athena.html)

CUR must use hourly or daily granularity. The query counts distinct usage dates across the account for each seven-day period. An empty period or fewer than seven populated dates stops the command with exit code 1, before printing or sending a cost report. Explicit zero-cost rows with full daily coverage remain valid. Wait for missing CUR data and rerun; an absent day is not treated as zero spending. Daily presence is a minimum check: it cannot prove that every service's charges have arrived, that AWS billing has finalized, or that OpenCost has every scrape within a day. Check Prometheus retention and restarts before comparing weeks; nonprod's ephemeral Prometheus storage loses history on Pod replacement, while the production profile uses a persistent volume.

The synthetic CUR CSV includes `usage_days` as its sixth column, matching the Athena query result. Its value describes coverage of the entire period, not the individual service or team row.

## Cloud Custodian policies

```bash
python -m pip install '.[custodian]'
custodian validate custodian/policies/*.yml
custodian run --dryrun --region us-east-1 --output-dir output custodian/policies/*.yml
finops waste --input output --dry-run
```

Configure `AWS_REGION` and `AWS_CUSTODIAN_ROLE_ARN` as GitHub repository variables to enable the scheduled workflow on `main`. Its role must trust the repository's GitHub OIDC subject for `refs/heads/main` and have read permissions for the queried EC2, ELBv2, and CloudWatch APIs. The workflow uploads the aggregate Markdown summary as an artifact. Optionally set repository variable `NOTIFIER` to `slack` or `telegram` and the corresponding destination credentials as repository secrets. The final step sends the completed report or a generic workflow failure notice. Configure notification routing separately for runs that cannot start or check out the repository.

The policies report candidates for review and define no resource actions. The EBS filter checks that an available volume was created over seven days ago. Snapshot age alone gives no retention decision, and the full source volume size is a proxy for snapshot storage. The ALB estimate uses a flat hourly charge with zero requests as the candidate signal. Waste amounts use a 730-hour month and these illustrative US East defaults:

| Environment variable / GitHub repository variable | Default USD rate |
| --- | ---: |
| `EBS_GB_MONTH_RATE` | 0.08 per GB-month |
| `SNAPSHOT_GB_MONTH_RATE` | 0.05 per GB-month |
| `EIP_HOURLY_RATE` | 0.005 per hour |
| `ALB_HOURLY_RATE` | 0.0225 per hour |

Override them for the region and storage class being scanned. Blank values retain
defaults; zero is allowed, while negative, nonfinite or malformed values fail
without printing a partial report. These are flat-rate estimates and exclude
ALB capacity charges, provisioned IOPS and snapshot incremental-storage details.
Verify billing data, usage, and ownership before making changes.

## Development

```bash
python -m pip install '.[dev,custodian]'
make lint test run
```

## Deployment

1. After the release checks pass, push the `v0.9` tag (Python package version `0.9.0`). `release.yml` runs the same tests, lint, policy validation and container smoke checks as pull requests, then scans the release image with Trivy. HIGH/CRITICAL findings block publication to `ghcr.io/<owner>/finops-toolkit:<tag>`.
2. Update the image tag in
   [`gitops-config/platform/finops-reporter/cronjob.yaml`](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/blob/main/gitops-config/platform/finops-reporter/cronjob.yaml)
   through a pull request and enable the optional reporter Application.
3. To include CUR, use the Terraform [reporting module](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/blob/main/platform-infra/modules/cost-reporting/README.md) to create the catalog, workgroup, results bucket and optional IRSA role. Copy its runtime environment outputs and ServiceAccount role annotation into GitOps. Configure notification credentials through the GitOps repository's secret workflow.
