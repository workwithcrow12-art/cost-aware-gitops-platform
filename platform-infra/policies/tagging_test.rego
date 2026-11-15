package main

import rego.v1

test_denies_missing_owner if {
	plan := {"resource_changes": [{
		"address": "module.network.aws_vpc.this",
		"mode": "managed",
		"type": "aws_vpc",
		"change": {"actions": ["create"], "after": {"tags_all": {
			"team": "platform", "env": "nonprod", "project": "cost-aware-gitops",
		}}},
	}]}
	denials := deny with input as plan
	denials == {"module.network.aws_vpc.this is missing the owner tag"}
}

test_accepts_inherited_tags_and_ignores_untaggable_resources if {
	plan := {"resource_changes": [{
		"address": "module.cluster.aws_eks_cluster.this",
		"mode": "managed",
		"type": "aws_eks_cluster",
		"change": {"actions": ["update"], "after": {"tags_all": {
			"team": "platform", "env": "nonprod", "project": "cost-aware-gitops", "owner": "platform",
		}}},
	}, {
		"address": "module.network.aws_route_table_association.private",
		"mode": "managed",
		"type": "aws_route_table_association",
		"change": {"actions": ["create"], "after": {}},
	}, {
		"address": "module.network.aws_vpc.old",
		"mode": "managed",
		"type": "aws_vpc",
		"change": {"actions": ["delete"], "after": null},
	}]}
	denials := deny with input as plan
	count(denials) == 0
}
