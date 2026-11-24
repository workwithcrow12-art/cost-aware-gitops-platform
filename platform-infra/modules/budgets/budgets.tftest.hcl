mock_provider "aws" {}

variables {
  name              = "test-monthly-budget"
  monthly_limit_usd = 200
  email             = "finops@example.com"
}

run "account_budget_defaults" {
  command = plan

  assert {
    condition = (
      aws_budgets_budget.monthly.limit_amount == "200" &&
      aws_budgets_budget.monthly.limit_unit == "USD" &&
      length(aws_budgets_budget.monthly.notification) == 2 &&
      length(aws_budgets_budget.monthly.cost_filter) == 0
    )
    error_message = "Default budget must configure 80% actual and 100% forecasted USD notifications."
  }
}

run "environment_filtered_budget" {
  command = plan

  variables {
    additional_emails         = ["platform@example.com"]
    subscriber_sns_topic_arns = ["arn:aws:sns:ap-southeast-1:123456789012:finops-alerts"]
    cost_filters = {
      TagKeyValue = ["user:env$nonprod"]
    }
    cost_types = {
      include_credit = false
      include_refund = false
      use_amortized  = true
    }
  }

  assert {
    condition = (
      length(aws_budgets_budget.monthly.cost_filter) == 1 &&
      aws_budgets_budget.monthly.cost_types[0].use_amortized &&
      !aws_budgets_budget.monthly.cost_types[0].include_credit
    )
    error_message = "Filtered budget must apply tag filters and amortized cost settings."
  }
}

run "reject_invalid_email_and_limit" {
  command = plan

  variables {
    monthly_limit_usd = 0
    email             = "not-an-email"
  }

  expect_failures = [var.monthly_limit_usd, var.email]
}
