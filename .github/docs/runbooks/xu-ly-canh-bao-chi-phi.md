# Investigate an AWS budget alert

1. Note the account, budget, alert time and billing period.
2. Check AWS billing grouped by service and active allocation tags. Compare the same dates with OpenCost
   to identify which namespaces or teams changed.
   If the FinOps CLI reports incomplete daily data, check CUR delivery and Prometheus history before rerunning. A missing day is not zero cost; a Prometheus Pod replacement can discard the lab's ephemeral history.
3. Compare the start of the change with recent Terraform, image-promotion and schedule changes.
4. Review the Cloud Custodian output for waste candidates. Confirm ownership, usage and recovery requirements
   before taking any action on a resource.
5. Record the cause and verify the cost trend after the next billing data refresh.
