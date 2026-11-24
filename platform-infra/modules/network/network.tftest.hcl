mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["ap-southeast-1a", "ap-southeast-1b", "ap-southeast-1c"] }
  }
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
  name       = "net-test"
  vpc_cidr   = "10.30.0.0/16"
  az_count   = 2
  nat_per_az = false
}

run "default_s3_gateway_and_encrypted_flow_logs" {
  command = plan

  assert {
    condition = (
      length(aws_subnet.private) == 2 &&
      length(aws_nat_gateway.this) == 1 &&
      length(aws_vpc_endpoint.s3) == 1 &&
      aws_vpc_endpoint.s3[0].vpc_endpoint_type == "Gateway" &&
      length(aws_vpc_endpoint.interface) == 0 &&
      aws_kms_key.flow_logs.enable_key_rotation &&
      aws_flow_log.this.traffic_type == "ALL"
    )
    error_message = "Default network must create a shared NAT, free S3 Gateway endpoint, and KMS-encrypted VPC flow logs."
  }
}

run "ha_nat_and_interface_endpoints" {
  command = plan

  variables {
    az_count                   = 3
    nat_per_az                 = true
    enable_interface_endpoints = true
  }

  assert {
    condition = (
      length(aws_nat_gateway.this) == 3 &&
      length(aws_vpc_endpoint.interface) == 4 &&
      aws_vpc_security_group_ingress_rule.endpoints_https[0].from_port == 443
    )
    error_message = "HA mode with interface endpoints must create 3 NAT gateways and ECR/STS/Logs interface endpoints."
  }
}

run "reject_invalid_cidr_and_az_count" {
  command = plan

  variables {
    vpc_cidr = "0.0.0.0/0"
    az_count = 1
  }

  expect_failures = [var.vpc_cidr, var.az_count]
}
