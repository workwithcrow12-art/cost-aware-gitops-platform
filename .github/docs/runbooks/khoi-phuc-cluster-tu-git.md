# Rebuild the nonprod cluster

Use an AWS lab account and check your account identity and budget before provisioning. The control
plane and network resources incur charges while the cluster exists. Clone `platform-infra` and
`gitops-config` side by side and follow their READMEs for tool versions and repository settings.

The dev and staging workloads run from 08:00 to 20:00 on weekdays in Asia/Ho_Chi_Minh.
For a demo outside that window, adjust the dev namespace's `downscaler/uptime` annotation in GitOps before bootstrapping.

1. If this account lacks a Terraform state backend, create one from `platform-infra`.

   ```bash
   terraform -chdir=bootstrap/state-backend init
   terraform -chdir=bootstrap/state-backend apply
   ```

   Reuse the existing state bucket and keys when recovering an existing environment.

2. Set the backend settings, the operator IAM role and the source CIDR that can reach the private EKS API.
   Run bootstrap from a host with routed access and DNS resolution in the VPC.

   ```bash
   export STATE_BUCKET="$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_name)"
   export STATE_BUCKET_REGION="$(terraform -chdir=bootstrap/state-backend output -raw state_bucket_region)"
   export TF_VAR_operator_role_arn='arn:aws:iam::123456789012:role/ClusterOperator'
   export TF_VAR_operator_access_cidrs='["10.20.1.0/24"]'
   make plan ENV=nonprod
   make apply ENV=nonprod
   ```

3. Bootstrap Argo CD with the checked-out config repository while authenticated as the operator.
   Set `EKS_OPERATOR_PROFILE` if you use a separate AWS CLI profile for this role.

   ```bash
   bash scripts/bootstrap-argocd.sh nonprod ../gitops-config
   kubectl -n argocd get applications,applicationsets
   ```

4. Create and commit the sealed Redis credential for dev using the GitOps README. Wait for the dev application
   to become healthy, then use a local port forward to verify that the storefront responds.

   ```bash
   kubectl -n boutique-dev get rollout frontend
   kubectl -n boutique-dev port-forward svc/frontend 8080:8080
   ```

   Open `http://localhost:8080` after the port forward starts. In a separate terminal, run the checkout smoke test from the `boutique-app` checkout:

   ```bash
   python .github/scripts/smoke-checkout.py --base-url http://localhost:8080
   ```

   Keep its exit status and deployed image revision with the lab evidence. This creates a synthetic order using the demo payment and email services.
5. Record the Terraform start time, Argo CD bootstrap time and first successful storefront response.
   For a disposable lab, use the teardown procedure in the infrastructure README.
