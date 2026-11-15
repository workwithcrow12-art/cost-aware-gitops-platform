# Athena reporting

Creates an Athena workgroup with a 5 GiB per-query scan limit. Existing callers can supply `results_s3` and optional `results_bucket_owner` for the original workgroup-only mode. Athena verifies the bucket owner, defaulting to the current account. A missing trailing `/` is added to the results prefix.

When `results_s3` is null, the module creates a separate results bucket with public access blocked, SSE-S3 encryption and a TLS-only policy. It does not force-delete query results during teardown. The AWS provider's default tags apply to supported resources, as in the shared bootstrap.

## Catalog and reporter role

```hcl
module "reporting" {
  source = "../../modules/cost-reporting"
  name   = "cost-aware-finops"
  cur_catalog = {
    database_name = "finops"
    table_name    = "cur"
    data_s3       = "s3://existing-billing-bucket/cur/parquet-data/"
  }
  reporter = {
    oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
    oidc_issuer_url   = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
  }
}
```

Alternatively set `athena_cur_catalog` and `athena_reporter` in the [shared bootstrap](../../bootstrap/state-backend/main.tf). Its outputs `athena_reporter_environment` and `athena_reporter_role_arn` connect the module to the FinOps CLI/CronJob. The module outputs are `workgroup_name`, `results_s3`, `reporter_environment` and `reporter_role_arn`.

`cur_catalog` creates a Glue database and an external Parquet table containing the five fields used by the packaged FinOps query:

| Legacy CUR field | Glue type |
| --- | --- |
| `line_item_usage_start_date` | `timestamp` |
| `line_item_product_code` | `string` |
| `line_item_unblended_cost` | `double` |
| `resource_tags_user_env` | `string` |
| `resource_tags_user_team` | `string` |

Use an existing legacy CUR with DAILY or HOURLY granularity, USD unblended costs and activated `team`/`env` cost allocation tags. Point `data_s3` at the folder containing only CUR Parquet data, including its dated subdirectories. Exclude manifest JSON, SQL scripts, CSV, duplicate report versions and Athena query results. This small unpartitioned table reads the supplied prefix recursively and is intended for a lab; the scan cap can reject larger histories. Reuse an existing partitioned CUR catalog/workgroup instead when the data exceeds that cap. Do not point it at CUR 2.0 or FOCUS data: their schemas differ. Billing export creation/delivery remains an account-level prerequisite. [AWS CUR Athena documentation](https://docs.aws.amazon.com/cur/latest/userguide/cur-query-athena.html)

`reporter` is optional and requires `cur_catalog`. Its trust policy binds the matching OIDC issuer, audience `sts.amazonaws.com` and only `system:serviceaccount:finops:finops-reporter`. The role can query this workgroup, read this Glue catalog/table and CUR prefix, and read/write only the results prefix. It cannot delete billing data. Cross-account bucket policies and KMS permissions for customer-managed encrypted source data remain owner configuration; the module does not expand IAM to accommodate them automatically.

Set the ServiceAccount annotation `eks.amazonaws.com/role-arn` to `reporter_role_arn`. Copy `reporter_environment` into the CronJob's environment (`AWS_REGION`, `ATHENA_DATABASE`, `ATHENA_TABLE`, `ATHENA_WORKGROUP`, `ATHENA_OUTPUT_S3`). Use the same AWS region for CUR data, Glue and Athena results. A managed IAM role here is for EKS IRSA; GKE/AKS use the FOCUS billing command without this AWS identity setup.
