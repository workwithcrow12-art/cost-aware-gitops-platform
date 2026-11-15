# AWS budget

Creates an account-wide monthly USD budget with an email notification above 80% actual and above 100% forecast spend. Supply `name`, `monthly_limit_usd` and `email`. The `budget_name` output identifies the budget created by the [shared bootstrap](../../bootstrap/state-backend/main.tf).
