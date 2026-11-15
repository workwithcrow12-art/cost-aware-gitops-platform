package main

import rego.v1

# These managed resource types support AWS provider default tags.
tagged_types := {
	"aws_athena_workgroup",
	"aws_budgets_budget",
	"aws_cloudwatch_log_group",
	"aws_eip",
	"aws_eks_addon",
	"aws_eks_access_entry",
	"aws_eks_cluster",
	"aws_eks_node_group",
	"aws_flow_log",
	"aws_iam_openid_connect_provider",
	"aws_iam_role",
	"aws_internet_gateway",
	"aws_launch_template",
	"aws_nat_gateway",
	"aws_route_table",
	"aws_s3_bucket",
	"aws_subnet",
	"aws_vpc",
	"aws_vpc_security_group_ingress_rule",
}

required_tags := {"team", "env", "project", "owner"}

deny contains message if {
	some resource in input.resource_changes
	resource.mode == "managed"
	resource.type in tagged_types
	some action in resource.change.actions
	action in {"create", "update"}
	some tag in required_tags
	trim_space(object.get(resource.change.after, ["tags_all", tag], "")) == ""
	message := sprintf("%s is missing the %s tag", [resource.address, tag])
}
