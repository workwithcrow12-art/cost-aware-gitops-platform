mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { region = "ap-southeast-1" }
  }
}

variables {
  cluster_name      = "cost-aware-nonprod"
  oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
  oidc_issuer_url   = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
}

run "provisions_scoped_irsa_node_role_and_interruption_queue" {
  command = plan

  assert {
    condition = (
      aws_sqs_queue.interruption.sqs_managed_sse_enabled &&
      length(aws_cloudwatch_event_rule.interruption) == 4 &&
      aws_eks_access_entry.node.type == "EC2_LINUX" &&
      jsondecode(aws_iam_role.controller.assume_role_policy).Statement[0].Condition.StringEquals["oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE:sub"] == "system:serviceaccount:kube-system:karpenter" &&
      jsondecode(aws_iam_role.controller.assume_role_policy).Statement[0].Condition.StringEquals["oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE:aud"] == "sts.amazonaws.com"
    )
    error_message = "Karpenter module must create an encrypted interruption queue, four EventBridge rules, and an audience/ServiceAccount-bound controller role."
  }
}

run "rejects_trailing_slash_on_issuer" {
  command = plan

  variables {
    oidc_issuer_url = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE/"
  }

  expect_failures = [var.oidc_issuer_url]
}
