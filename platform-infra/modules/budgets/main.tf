locals {
  subscriber_emails = toset(concat([var.email], tolist(var.additional_emails)))
}

resource "aws_budgets_budget" "monthly" {
  name         = var.name
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "cost_filter" {
    for_each = var.cost_filters
    content {
      name   = cost_filter.key
      values = cost_filter.value
    }
  }

  dynamic "cost_types" {
    for_each = var.cost_types == null ? [] : [var.cost_types]
    content {
      include_credit  = cost_types.value.include_credit
      include_refund  = cost_types.value.include_refund
      include_support = cost_types.value.include_support
      include_tax     = cost_types.value.include_tax
      use_amortized   = cost_types.value.use_amortized
    }
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = local.subscriber_emails
    subscriber_sns_topic_arns  = var.subscriber_sns_topic_arns
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = local.subscriber_emails
    subscriber_sns_topic_arns  = var.subscriber_sns_topic_arns
  }
}
