package main

import rego.v1

full_tags := {
	"team": "platform",
	"env": "nonprod",
	"project": "cost-aware-gitops",
	"owner": "platform",
}

test_denies_missing_owner_across_aws_azure_and_gcp if {
	incomplete := {"team": "platform", "env": "nonprod", "project": "cost-aware-gitops"}
	plan := {"resource_changes": [
		{
			"address": "module.cluster.aws_kms_key.cluster",
			"mode": "managed",
			"type": "aws_kms_key",
			"change": {"actions": ["create"], "after": {"tags_all": incomplete}},
		},
		{
			"address": "azurerm_kubernetes_cluster.this",
			"mode": "managed",
			"type": "azurerm_kubernetes_cluster",
			"change": {"actions": ["create"], "after": {"tags": incomplete}},
		},
		{
			"address": "google_container_cluster.this",
			"mode": "managed",
			"type": "google_container_cluster",
			"change": {"actions": ["create"], "after": {"resource_labels": incomplete}},
		},
	]}
	denials := deny with input as plan
	denials == {
		"module.cluster.aws_kms_key.cluster is missing the owner tag",
		"azurerm_kubernetes_cluster.this is missing the owner tag",
		"google_container_cluster.this is missing the owner label",
	}
}

test_accepts_inherited_tags_multi_cloud_and_ignores_untaggable_resources if {
	plan := {"resource_changes": [
		{
			"address": "module.cluster.aws_eks_cluster.this",
			"mode": "managed",
			"type": "aws_eks_cluster",
			"change": {"actions": ["update"], "after": {"tags_all": full_tags}},
		},
		{
			"address": "module.cost_reporting.aws_glue_catalog_database.cur[0]",
			"mode": "managed",
			"type": "aws_glue_catalog_database",
			"change": {"actions": ["create"], "after": {"tags_all": full_tags}},
		},
		{
			"address": "module.cost_reporting.aws_glue_catalog_table.cur[0]",
			"mode": "managed",
			"type": "aws_glue_catalog_table",
			"change": {"actions": ["create"], "after": {}},
		},
		{
			"address": "azurerm_resource_group.this",
			"mode": "managed",
			"type": "azurerm_resource_group",
			"change": {"actions": ["create"], "after": {"tags": full_tags}},
		},
		{
			"address": "google_container_node_pool.system",
			"mode": "managed",
			"type": "google_container_node_pool",
			"change": {"actions": ["create"], "after": {"node_config": [{"resource_labels": full_tags}]}},
		},
		{
			"address": "module.network.aws_route_table_association.private",
			"mode": "managed",
			"type": "aws_route_table_association",
			"change": {"actions": ["create"], "after": {}},
		},
		{
			"address": "module.network.aws_vpc.old",
			"mode": "managed",
			"type": "aws_vpc",
			"change": {"actions": ["delete"], "after": null},
		},
	]}
	denials := deny with input as plan
	count(denials) == 0
}
