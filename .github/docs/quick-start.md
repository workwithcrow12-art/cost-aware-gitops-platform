# Bắt đầu với Cost-aware GitOps Platform

## 1. Hiểu luồng giữa các repo

| Repo | Việc cần làm ở đây | Kết quả chuyển sang repo khác |
| --- | --- | --- |
| `platform-infra` | Terraform tạo cluster, mạng, quyền truy cập; bootstrap Argo CD | Kubernetes context cho `gitops-config`; cấu hình Athena cho reporter |
| `gitops-config` | Argo CD cài platform add-on và Boutique từ Git | OpenCost cung cấp allocation API cho `finops-toolkit` |
| `boutique-app` | Kiểm thử, build, scan image; đề xuất digest qua PR | Digest được review và promote trong `gitops-config` |
| `finops-toolkit` | Báo cáo OpenCost, Athena và CSV billing nhiều cloud | Markdown ở stdout; thông báo là cấu hình tùy chọn |
| `.github` | Kiến trúc, runbook và bằng chứng kiểm tra | Điểm bắt đầu để chọn đúng quy trình |

Từ v0.9, clone repository chung rồi chạy lệnh trong thư mục thành phần tương ứng. CI hoạt động ở `.github/workflows` tại root; các workflow lồng trong thành phần chỉ là ví dụ standalone.

```bash
git clone https://github.com/workwithcrow12-art/cost-aware-gitops-platform.git
cd cost-aware-gitops-platform
```

## 2. Demo offline trước, không cần tài khoản cloud

Cần Python 3.11 trở lên. Từ thư mục chứa các repo, chạy PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path finops-toolkit/src).Path
python -m unittest discover -s finops-toolkit/tests -v
python -m finops.cli report --fixtures finops-toolkit/tests/fixtures
python -m finops.cli cloud-report --input finops-toolkit/tests/fixtures/focus_sample.csv --as-of 2026-01-19
python -m finops.cli waste --input finops-toolkit/tests/fixtures/custodian --dry-run
```

Với Bash, thay dòng đầu bằng `export PYTHONPATH="$PWD/finops-toolkit/src"`. Dữ liệu minh họa là dữ liệu tổng hợp: báo cáo cloud có 43.75 USD mỗi tuần, gồm AWS 8.75, Google Cloud 14.00 và Microsoft Azure 21.00 USD. Đây không phải chi phí đo từ cloud. Lệnh `cloud-report` chỉ đọc CSV và in báo cáo, không gửi thông báo.

## 3. Chọn một cluster để triển khai lab

| Cloud | Terraform root trong `platform-infra` | Đăng nhập và truy cập |
| --- | --- | --- |
| AWS | `envs/nonprod`, `envs/prod` | Theo [runbook EKS](runbooks/khoi-phuc-cluster-tu-git.md) để tạo state backend và operator role |
| GCP | `envs/gke` | Project đã bật billing; `gcloud auth application-default login`; cài `gke-gcloud-auth-plugin` |
| Azure | `envs/aks` | Subscription và Entra group có sẵn; `az login`; cài `kubelogin` |

Các lệnh cloud bên dưới tạo tài nguyên tính phí khi bạn tự chạy `terraform apply`. Hai cấu hình mới là lab nonprod, mỗi cluster có hai node cố định. Chúng chưa được kiểm chứng bằng triển khai cloud thật. GKE là cluster một zone; AKS dùng cấu hình lab mặc định, không phải thiết kế HA production.

Với GKE, chạy từ `platform-infra`:

```bash
cp envs/gke/terraform.tfvars.example envs/gke/lab.secret.tfvars
# Điền project_id, operator_member và CIDR VPN/bastion trong file vừa tạo.
terraform -chdir=envs/gke init
terraform -chdir=envs/gke plan -var-file=lab.secret.tfvars -out=lab.tfplan
terraform -chdir=envs/gke apply lab.tfplan
terraform -chdir=envs/gke output -raw get_credentials_command
# Chạy lệnh gcloud được in ra ở trên từ host có đường đến private API.
```

Với AKS:

```bash
cp envs/aks/terraform.tfvars.example envs/aks/lab.secret.tfvars
# Điền subscription_id, tenant_id và operator_group_object_id.
terraform -chdir=envs/aks init
terraform -chdir=envs/aks plan -var-file=lab.secret.tfvars -out=lab.tfplan
terraform -chdir=envs/aks apply lab.tfplan
terraform -chdir=envs/aks output -raw get_credentials_command
# Chạy lệnh az được in ra ở trên, rồi chuyển kubeconfig sang Entra login:
kubelogin convert-kubeconfig -l azurecli
```

GKE/AKS dùng state riêng tại từng root, mặc định local cho một người chạy lab. Với nhóm làm việc, thêm backend GCS/Azure Blob và chuyển state bằng `terraform init -migrate-state` trước khi chia sẻ; không dùng chung state/key với EKS. Không commit state hoặc kubeconfig.

Tất cả cluster có API riêng tư. Operator cần VPN/bastion trong mạng có route và DNS phù hợp; Terraform không tạo kết nối từ laptop. GKE giới hạn thêm CIDR operator; tránh trùng các dải node/pod/service cố định trong cấu hình với mạng đã kết nối. AKS cấp quyền Kubernetes qua Entra group, không bật local admin. Tài khoản chạy Terraform cần quyền tạo tài nguyên và IAM/role assignments; GKE còn cần quyền bật APIs. `roles/container.admin` của operator GKE áp dụng cho project lab đã chọn.

GKE dùng Dataplane V2, AKS dùng Calico để thực thi NetworkPolicy. Firewall GKE cho control plane truy cập Kyverno TCP 9443, theo [hướng dẫn Kyverno](https://kyverno.io/docs/troubleshooting/). Node GKE dùng service account riêng với [role tối thiểu của GKE](https://docs.cloud.google.com/kubernetes-engine/security/configure-node-service-accounts).

## 4. Bootstrap cùng một cấu hình GitOps

Push các repo fork trước; sửa URL owner/repository trong `gitops-config/bootstrap`, `applicationsets` và `platform/*-app.yaml` như hướng dẫn trong README repo. Với repo private, thêm credential vào Argo CD. Chuẩn bị Redis Sealed Secret theo README `gitops-config` trước khi sync Boutique.

Từ `platform-infra`, với GKE/AKS đã lấy kubeconfig:

```bash
kubectl config get-contexts
# Thay context dưới đây bằng output kube_context của Terraform root đã chọn.
bash scripts/bootstrap-argocd.sh nonprod ../gitops-config YOUR_KUBE_CONTEXT managed
```

Script truyền context tường minh cho Helm/kubectl. Profile `managed` chọn root `nonprod-managed`, kế thừa nonprod nhưng bỏ chart metrics-server để dùng thành phần do GKE/AKS quản lý. Không truyền tham số thứ ba/thứ tư thì script giữ đường bootstrap EKS hiện có. Root `nonprod` cài dev, staging, preview và downscaler; root `prod` dành cho cluster production riêng. Profile `managed` hiện chỉ dành cho nonprod.

ApplicationSet `platform-addons` tự cài OpenCost Helm chart `2.5.20` và Prometheus; không cần chạy một bản OpenCost sandbox hoặc cài Helm release thứ hai. Sau khi Argo CD đồng bộ add-on, kiểm tra:

```bash
kubectl --context YOUR_KUBE_CONTEXT -n argocd get applications
kubectl --context YOUR_KUBE_CONTEXT -n opencost rollout status deployment/opencost --timeout=10m
kubectl --context YOUR_KUBE_CONTEXT -n opencost port-forward svc/opencost 9003:9003
# Ở terminal khác:
curl --fail 'http://localhost:9003/allocation?window=1h&aggregate=namespace,label:env,label:team'
```

Nếu deployment chưa tồn tại, xem trạng thái `platform-opencost`, `platform-monitoring` và `platform-addons` trong Argo CD. Nếu API chưa có allocation, kiểm tra Prometheus và chờ metrics. Báo cáo so sánh tuần cần 14 ngày UTC đã hoàn tất. Prometheus lab dùng storage tạm; Pod thay thế có thể làm mất lịch sử. Dùng storage bền vững trước khi phụ thuộc vào báo cáo định kỳ.

## 5. Athena: tự tạo catalog, results bucket và quyền reporter

Phần này chỉ dành cho AWS billing. Tạo legacy CUR xuất Parquet với granularity DAILY hoặc HOURLY và bật cost allocation tags `team`, `env`. Việc bật billing export/đợi AWS phân phối dữ liệu vẫn thuộc tài khoản billing. Module không tự tạo hóa đơn hoặc mô phỏng dữ liệu live.

Thêm vào file `*.secret.tfvars` dùng cho `platform-infra/bootstrap/state-backend`:

```hcl
athena_cur_catalog = {
  database_name = "finops"
  table_name    = "cur"
  data_s3       = "s3://YOUR-CUR-BUCKET/path/to/parquet-data/"
}
athena_reporter = {
  oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/YOUR-ID"
  oidc_issuer_url   = "https://oidc.eks.ap-southeast-1.amazonaws.com/id/YOUR-ID"
}
```

Sử dụng đúng OIDC provider của cluster EKS đang chạy reporter. Nếu chỉ chạy CLI bằng một IAM identity đã có quyền, bỏ `athena_reporter`. Chạy `plan` rồi `apply` root bootstrap với cùng input/state đã dùng để tạo state backend; giữ nguyên bucket state và budget hiện có.

Khi `athena_results_s3` để null, module tạo bucket results riêng, private, mã hóa và bắt buộc TLS; đồng thời tạo Glue database/table và workgroup có giới hạn scan 5 GiB mỗi query. Khi đã có results prefix, vẫn dùng được chế độ workgroup cũ. Module hỗ trợ legacy CUR Parquet với schema trong [README module](https://github.com/workwithcrow12-art/cost-aware-gitops-platform/blob/main/platform-infra/modules/cost-reporting/README.md), không tự nhận CUR 2.0/FOCUS.

```bash
terraform -chdir=bootstrap/state-backend output -json athena_reporter_environment
terraform -chdir=bootstrap/state-backend output -raw athena_reporter_role_arn
```

Đưa các biến môi trường đầu ra vào `gitops-config/platform/finops-reporter/cronjob.yaml`; gán ARN role cho annotation `eks.amazonaws.com/role-arn` trên ServiceAccount `finops-reporter`. IAM role chỉ tin `system:serviceaccount:finops:finops-reporter`. Quyền đọc CUR và đọc/ghi kết quả giới hạn theo prefix; không có quyền sửa/xóa billing data. Bật Application reporter theo README GitOps và publish đúng image trước khi chạy CronJob.

## 6. Tổng hợp billing AWS/GCP/Azure

Xuất billing về CSV theo [FOCUS 1.0/1.1](https://focus.finops.org/wp-content/uploads/2024/11/FOCUS-spec-v1_1.pdf), hoặc chuyển đổi export gốc sang các cột mà CLI đọc. Xem hợp đồng dữ liệu và ví dụ trong README `finops-toolkit`. Gộp các dòng vào **một CSV, một header**, giữ ProviderName nhất quán và không đưa cùng charge vào hai lần.

```bash
# Từ finops-toolkit, sau khi cài python -m pip install .:
finops cloud-report --input exports/combined-focus.csv --as-of 2026-01-19
```

CLI nhóm theo provider, environment và team, tách từng BillingCurrency, không quy đổi ngoại tệ và không cộng vào OpenCost. Mỗi provider xuất hiện trong hai tuần phải có dòng dữ liệu cho đủ 14 ngày. Dòng có chi phí 0 hoặc credit âm được giữ; ngày thiếu không được coi là 0. Kiểm tra này không phát hiện được một provider bị bỏ hoàn toàn khỏi file, charge trùng lặp hay hóa đơn chưa hoàn tất. Cần đối chiếu export nguồn trước khi đưa ra quyết định chi phí.

## 7. Kiểm tra trước khi mở PR

Từ `platform-infra` với Terraform 1.11.4 và kết nối tải provider:

```bash
make validate
python3 -m unittest discover -s tests -v
```

`make validate` chạy fmt, validate và mock plans cho AWS bootstrap/nonprod/prod, GKE, AKS và module Athena; không dùng credential cloud. Hai workflow apply/drift vẫn dành cho EKS; GKE/AKS được provision bằng lệnh root tương ứng ở trên.

Từ `gitops-config`:

```bash
kyverno test platform/kyverno/tests
```

CI đã chạy Kyverno CLI trên PR/push; bộ test kiểm tra cả Pod, initContainer, Deployment và phạm vi namespace. Không cần tạo cluster kuttl chỉ để kiểm tra các rule hiện tại. Render/schema checks và Redis image scan vẫn nằm trong workflow `Validate GitOps`.

Từ `finops-toolkit`:

```bash
python -m pip install '.[dev]'
make lint test
finops cloud-report --input tests/fixtures/focus_sample.csv --as-of 2026-01-19
```

Mock plans, policy tests và render checks là bằng chứng cục bộ. Trước khi dùng cloud thật, vẫn cần kiểm chứng quyền provider, quota, private networking, sync controllers, giá OpenCost và dữ liệu billing thực tế.
