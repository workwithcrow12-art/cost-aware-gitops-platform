# Ghi bằng chứng lab AWS nonprod

## Trạng thái ngày 2026-11-16

**Chưa chạy lab cloud. Không tạo tài nguyên AWS.** Chủ dự án yêu cầu chỉ dùng Free Tier và không phát sinh phí. Máy hiện chưa có AWS CLI, Terraform, kubectl, Helm trong PATH; không có AWS profile/config/credentials hoặc kubeconfig. Tên profile được cung cấp trong chat chưa phải một phiên đăng nhập có thể sử dụng tại máy.

Kiến trúc hiện tại tạo EKS, hai worker Spot `m6i.large`/`m6a.large`/`m5.large`, một NAT Gateway nonprod, EBS và logging. Không thể xác nhận tổng chi phí bằng 0 chỉ từ nhãn Free Tier:

- [EKS pricing](https://aws.amazon.com/eks/pricing/) công bố phí control plane theo giờ; mức standard support tại thời điểm kiểm tra là $0.10/cluster/giờ, chưa gồm worker và mạng.
- [AWS Free Tier](https://aws.amazon.com/free/) phân biệt Free plan có credit/thời hạn và Paid plan. Credit hoặc quyền dùng một dịch vụ không chứng minh toàn bộ lab nằm trong hạn mức miễn phí của tài khoản này.
- Cần xác nhận plan, quyền dùng từng dịch vụ, credit còn lại và thời hạn trong Billing. Không nâng cấp tài khoản hay bật dịch vụ trả phí để vượt giới hạn đã yêu cầu.

Với giới hạn hiện tại, dùng [demo offline](../demo.md). Các bước bên dưới là kế hoạch cho lần chạy được phép sau khi các điều kiện chi phí và truy cập đã được xác minh; chúng chưa phải kết quả đo.

## Điều kiện trước khi provision

Ghi vào bản ghi riêng, không commit access key, token, account ID đầy đủ, ARN hoặc Terraform state:

| Điều kiện | Cần xác minh |
| --- | --- |
| Identity | AWS CLI đăng nhập bằng profile có thật; `aws sts get-caller-identity --profile "YOUR_PROFILE"` trả đúng tài khoản sandbox |
| Chi phí | Plan tài khoản, service eligibility, credit/hạn mức còn lại, region, thời lượng; ước tính tất cả EKS/EC2/NAT/EBS/logging/data transfer; không coi Budget là hard cap |
| Ngân sách | Giới hạn được chủ tài khoản chấp nhận và thời điểm teardown; với yêu cầu 0 phí, dừng nếu chưa chứng minh được phạm vi miễn phí |
| State | Dùng lại backend và state nếu đã có; không tạo cluster trùng khi khôi phục |
| Operator | IAM role, private source CIDR, host/VPN có route và DNS tới private EKS API; repo không tự tạo bastion/VPN |
| Desired state | Commit đã push vào repository Argo CD đọc; cấu hình URL/registry đúng; Redis Sealed Secret cho dev; không đưa plaintext secret vào log |
| Tools | AWS CLI, Bash, Make, Terraform/kubectl/Helm theo `platform-infra/.tool-versions`; Git và Python |

Không cần chạy 14 ngày chỉ để có demo: provisioning, checkout, lỗi canary, rollback có thể đo trong một phiên. Báo cáo tuần từ dữ liệu live cần riêng 14 ngày UTC hoàn tất và sẽ phát sinh thời gian lưu tài nguyên.

## Các bước chạy và bằng chứng cần giữ

Từ monorepo root, ghi `git rev-parse HEAD` và thời gian UTC vào thư mục riêng dưới `.scratch/aws-lab-<timestamp>`. Ghi exit status cho từng lệnh; không chia sẻ binary plan, raw state, secret YAML hoặc log chứa credential.

1. Theo [rebuild runbook](khoi-phuc-cluster-tu-git.md), từ `platform-infra` tạo/reuse backend, review plan nonprod rồi apply đúng cấu hình đã review. Ghi thời điểm bắt đầu/kết thúc, kết quả plan và region; dừng nếu identity, chi phí hoặc kế hoạch khác dự kiến.
2. Từ host có private access, bootstrap Argo CD. Ghi root path `gitops-config/bootstrap/nonprod`, source revision và kết quả `kubectl -n argocd get applications,applicationsets`. Chuẩn bị Secret theo README GitOps rồi chờ Boutique healthy.
3. Ghi image digest đang chạy và `kubectl -n boutique-dev get rollouts,analysisruns,pods`. Port-forward `svc/frontend 8080:8080`; ở terminal khác, từ `boutique-app` chạy:

   ```bash
   python .github/scripts/smoke-checkout.py --base-url http://localhost:8080
   ```

   Lưu exit code và xác nhận đơn hàng/giỏ hàng. Không dùng thẻ thật; dịch vụ payment/email là mock.
4. Chỉ trên **dev**, làm [canary drill](../postmortems/001-canary-tu-rollback.md): qua PR GitOps đổi `PRODUCT_CATALOG_SERVICE_ADDR` của candidate thành `missing-catalog:3550`. Ghi SHA của PR đã merge và timestamp rollout/analysis. Chứng minh AnalysisRun thất bại và kiểm tra stable vẫn phục vụ. Nếu kết quả khác, ghi đúng hiện tượng thay vì đánh dấu pass.
5. Revert đúng commit lỗi qua PR theo [rollback runbook](rollback-thu-cong.md); đợi Argo CD reconcile, chạy lại checkout smoke và lưu restored digest/timestamp. Nếu đã bật force-uptime, revert annotation đó.
6. Khi kết thúc phiên, kiểm tra và dọn các LB/PV do Kubernetes tạo trước khi theo teardown từ `platform-infra`. Chỉ destroy môi trường disposable đã xác định, giữ shared backend để bảo toàn state. Đối chiếu EKS, EC2, NAT, EBS/EIP và logs còn lại trong region; xem Billing sau khi dữ liệu cập nhật. `terraform destroy` thành công không đủ chứng minh hóa đơn cuối cùng bằng 0.

## Mẫu kết quả cho một lần chạy

Copy bảng này vào bằng chứng mới sau khi thực sự chạy. Không thay `NOT RUN` bằng kết quả dự kiến.

| Giai đoạn | UTC bắt đầu/kết thúc | Commit/digest | Kết quả / đường dẫn log |
| --- | --- | --- | --- |
| Identity và kiểm tra chi phí | — | — | NOT RUN |
| Plan/apply nonprod | — | — | NOT RUN |
| Argo CD/bootstrap healthy | — | — | NOT RUN |
| Checkout trước drill | — | — | NOT RUN |
| Canary lỗi / stable availability | — | — | NOT RUN |
| Revert / checkout sau rollback | — | — | NOT RUN |
| Teardown / residual-resource check | — | — | NOT RUN |
| Billing đối chiếu sau cập nhật | — | — | NOT RUN |

Tính recovery time từ lỗi được phát hiện đến checkout thành công sau phục hồi; tách riêng thời gian stable tiếp tục phục vụ và thời gian Git trở về trạng thái tốt. Chỉ công bố số đo có log và timestamp tương ứng.
