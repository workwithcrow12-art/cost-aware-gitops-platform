package main

import rego.v1

# AWS managed resource types that support tags_all via provider default_tags.
# Note: aws_glue_catalog_table is excluded because AWS Glue Tables do not support tags.
aws_tagged_types := {
	"aws_athena_workgroup",
	"aws_budgets_budget",
	"aws_cloudwatch_event_rule",
	"aws_cloudwatch_log_group",
	"aws_eip",
	"aws_eks_addon",
	"aws_eks_access_entry",
	"aws_eks_cluster",
	"aws_eks_node_group",
	"aws_flow_log",
	"aws_glue_catalog_database",
	"aws_iam_openid_connect_provider",
	"aws_iam_policy",
	"aws_iam_role",
	"aws_internet_gateway",
	"aws_kms_key",
	"aws_launch_template",
	"aws_nat_gateway",
	"aws_route_table",
	"aws_s3_bucket",
	"aws_security_group",
	"aws_sqs_queue",
	"aws_subnet",
	"aws_vpc",
	"aws_vpc_endpoint",
	"aws_vpc_security_group_ingress_rule",
}

azure_tagged_types := {
	"azurerm_kubernetes_cluster",
	"azurerm_resource_group",
	"azurerm_user_assigned_identity",
	"azurerm_virtual_network",
}

required_tags := {"team", "env", "project", "owner"}

active_change(resource) if {
	resource.mode == "managed"
	some action in resource.change.actions
	action in {"create", "update"}
}

deny contains message if {
	some resource in input.resource_changes
	active_change(resource)
	resource.type in aws_tagged_types
	some tag in required_tags
	trim_space(object.get(resource.change.after, ["tags_all", tag], "")) == ""
	message := sprintf("%s is missing the %s tag", [resource.address, tag])
}

deny contains message if {
	some resource in input.resource_changes
	active_change(resource)
	resource.type in azure_tagged_types
	some tag in required_tags
	trim_space(object.get(resource.change.after, ["tags", tag], "")) == ""
	message := sprintf("%s is missing the %s tag", [resource.address, tag])
}

gcp_cluster_label(after, tag) := val if {
	effective := object.get(after, ["effective_labels", tag], "")
	resource_lbl := object.get(after, ["resource_labels", tag], "")
	val := trim_space(concat("", [effective, resource_lbl]))
}

deny contains message if {
	some resource in input.resource_changes
	active_change(resource)
	resource.type == "google_container_cluster"
	some tag in required_tags
	gcp_cluster_label(resource.change.after, tag) == ""
	message := sprintf("%s is missing the %s label", [resource.address, tag])
}

gcp_pool_label(after, tag) := val if {
	cfg := object.get(after, ["node_config", 0], {})
	resource_lbl := object.get(cfg, ["resource_labels", tag], "")
	k8s_lbl := object.get(cfg, ["labels", tag], "")
	val := trim_space(concat("", [resource_lbl, k8s_lbl]))
}

deny contains message if {
	some resource in input.resource_changes
	active_change(resource)
	resource.type == "google_container_node_pool"
	some tag in required_tags
	gcp_pool_label(resource.change.after, tag) == ""
	message := sprintf("%s is missing the %s label", [resource.address, tag])
}
