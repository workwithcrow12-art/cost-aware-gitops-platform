# EKS cluster

Creates an EKS cluster with a private Kubernetes API, a managed AL2023 system node group, control-plane logs and an IAM OIDC provider for workloads using IAM roles for service accounts. The node group uses private subnets and reaches public image registries via NAT. The managed VPC CNI add-on enables Kubernetes NetworkPolicy enforcement in standard mode and uses a dedicated role for the `kube-system/aws-node` service account. Standard mode can allow a new pod's traffic until its policy has been programmed.

Supply the cluster `name`, `kubernetes_version`, private `subnet_ids`, `capacity_type`, `instance_types`, `node_count` and `cost_tags`. The cost tags must include non-empty `team`, `env`, `project` and `owner` values. Each environment shares its tag map between AWS provider defaults and the worker launch template, which tags both EC2 instances and their EBS volumes. `operator_role_arn` grants a specific IAM role cluster administrator access. `operator_access_cidrs` grants the routed operator network TCP 443 access to the private endpoint. Outputs are `name`, `arn`, `endpoint` and `oidc_provider_arn`. See [nonprod](../../envs/nonprod/main.tf) for Spot.

The launch template explicitly requires IMDSv2 and sets its response hop limit to 1, so ordinary pods cannot retrieve the node role's credentials through IMDS. This preserves the metadata isolation [AWS documents for default AL2023 managed node groups](https://docs.aws.amazon.com/eks/latest/userguide/al2023.html). Host-network pods can still reach instance metadata; workloads that need AWS permissions should use dedicated service-account roles.

## Migrate worker cost tags

Adding a custom launch template to an existing EKS managed node group requires a replacement group. The module uses a generated `system-` name and `create_before_destroy` so Terraform can create the replacement before deleting the old group. Review the plan for node group replacement and confirm it does not replace the EKS cluster. Allow EC2 capacity, subnet IPs and quota for both groups during the transition; temporary overlap incurs additional charges.

The Terraform deployment role needs launch-template management permissions and `ec2:RunInstances`/`ec2:CreateTags` for tagged nodes. Before applying to an existing cluster, check workload disruption budgets and persistent data. Creation before deletion does not guarantee uninterrupted application service. Redis in this lab uses ephemeral storage, so rescheduling it can lose carts.

After applying in a maintenance window, verify the replacement nodes are Ready, application health is restored, and EC2 instances and attached EBS volumes have all four cost tags. Activate `env` and `team` in AWS Billing and wait for fresh CUR records before checking allocation. Previously billed usage is not retagged by this change. See [AWS launch-template guidance](https://docs.aws.amazon.com/eks/latest/userguide/launch-templates.html).

## Migrate an existing cluster

Plan the move in a maintenance window. Prepare the private route and DNS and set the operator inputs before applying the updated Terraform. Inspect the plan for cluster replacement. The `ignore_changes` rule keeps the original cluster when only the creation-time administrator setting differs. The old creator's access entry must be revoked separately.

If the requested operator is already an EKS access entry that Terraform does not manage, import that entry and its existing cluster-admin policy association before applying. If the cluster already uses the AWS-managed `vpc-cni` add-on outside Terraform, import it into `module.cluster.aws_eks_addon.vpc_cni`. Existing Terraform-managed operator entries move automatically from their indexed addresses.

```bash
make init ENV=nonprod
cluster='cost-aware-nonprod'
admin_policy='arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy'

# Run only the imports for resources already present outside Terraform state.
terraform -chdir=envs/nonprod import module.cluster.aws_eks_access_entry.operator \
  "$cluster:$TF_VAR_operator_role_arn"
terraform -chdir=envs/nonprod import module.cluster.aws_eks_access_policy_association.operator \
  "$cluster#$TF_VAR_operator_role_arn#$admin_policy"
terraform -chdir=envs/nonprod import module.cluster.aws_eks_addon.vpc_cni "$cluster:vpc-cni"
```

For a cluster previously using the system node IAM role for VPC CNI, stage the managed add-on and operator access together. Use the environment name you intend to migrate.

```bash
make init ENV=nonprod
terraform -chdir=envs/nonprod plan \
  -target=module.cluster.aws_eks_access_policy_association.operator \
  -target=module.cluster.aws_vpc_security_group_ingress_rule.operator \
  -target=module.cluster.aws_eks_addon.vpc_cni \
  -out=migration.tfplan
terraform -chdir=envs/nonprod apply migration.tfplan
```

From the private network, confirm the explicit operator can access Kubernetes and that `aws-node` is healthy with the dedicated role. Then use `aws eks list-access-entries` and `aws eks list-associated-access-policies` to identify the original creator's access. If it differs from the explicit operator, remove the creator's cluster-admin policy with `aws eks disassociate-access-policy` or its entire entry with `aws eks delete-access-entry`. Recheck access before running a normal full plan and apply to remove the old CNI policy attachment from the node role. Verify VPC CNI policy enforcement and DNS with a new test pod before relying on workload isolation.
