# Đối chiếu và khắc phục bản đánh giá

Đối chiếu ngày 14/11/2026 với file `cost-aware-comparison.md` do người dùng cung cấp. Các giải pháp trong file được xem là đề xuất; lựa chọn triển khai dựa trên mã nguồn đang có.

| Điểm yếu được nêu | Trạng thái thực tế và thay đổi | Cách kiểm chứng |
| --- | --- | --- |
| Chỉ hỗ trợ AWS EKS | Thêm Terraform roots `envs/gke`, `envs/aks`: mạng, cluster private, node identity, operator access, network policy, cost labels/tags. Bootstrap hỗ trợ context tường minh và profile `managed` bỏ metrics-server trùng với cloud; giữ EKS discovery. | Terraform validate + mock plans; bootstrap tests. Chưa triển khai GKE/AKS thật. |
| Athena cần tạo DB/table/IAM thủ công | Module cũ chỉ tạo workgroup. Bổ sung results bucket private/mã hóa/TLS, Glue database/table cho legacy CUR Parquet, role IRSA giới hạn prefix, outputs cấu hình reporter; nối vào shared bootstrap. | Mock plans cho cấu hình đầy đủ, chế độ workgroup cũ, và input không hợp lệ. Billing export vẫn cần bật và có dữ liệu thật. |
| Thiếu tổng hợp chi phí nhiều cloud | Thêm `finops cloud-report` đọc CSV FOCUS; nhóm provider/env/team; tách tiền tệ; kiểm tra ngày và dữ liệu đầu vào. Không cần thêm dịch vụ Kubecost để đọc export. | Fixture AWS/GCP/Azure, unit tests, CLI và container smoke trong CI. Không tự tải export từ cloud API. |
| Phụ thuộc OpenCost sandbox | Bản repo hiện tại đã có Helm chart pin version trong ApplicationSet, tự sync qua Argo CD. Giữ một Helm release do GitOps quản lý, bổ sung quy trình kiểm tra deployment/API và xử lý thiếu metrics. | Kiểm tra chart package, ApplicationSet đã render và values Prometheus/ServiceMonitor. Việc sync cluster thật vẫn cần operator xác nhận. |
| Thiếu CI policy testing | Bản repo hiện tại đã chạy `kyverno test` trong GitHub Actions. Mở rộng từ 9 lên 19 kết quả kỳ vọng: partial limits, initContainer, Deployment autogen, namespace exclusions. | Kyverno CLI 1.18.1: 19 kết quả đạt. Không thêm stack kuttl trùng chức năng. |
| Khó hiểu liên kết nhiều repo | Thêm [quick-start tiếng Việt](quick-start.md) theo luồng offline → chọn cloud → bootstrap → billing → kiểm thử, có thư mục chạy lệnh và giới hạn rõ ràng. | Các lệnh offline, Terraform mock, bootstrap giả lập và manifest render. Giữ nguyên ranh giới repo. |

Các thay đổi có thể review trong từng repo, không yêu cầu provision cloud để chạy CI. Bằng chứng này không thay thế kiểm thử tích hợp trên EKS/GKE/AKS và đối chiếu hóa đơn thực tế.

## Kiểm chứng cục bộ

- Python: 28 unit tests cho FinOps và một bootstrap test với ba trường hợp EKS/context/profile.
- Terraform 1.11.4: fmt, validate và 15 mock plan cases trên sáu roots/module; có kiểm tra chế độ Athena cũ.
- Kyverno 1.18.1: 19 kết quả kỳ vọng đạt.
- Kustomize qua kubectl 1.35.2: render 11 roots. Kubeconform: 142 resources hợp lệ, 40 custom resources bỏ qua do thiếu schema, không lỗi/không resource sai.
- Actionlint: ba workflows đã sửa đạt kiểm tra; ShellCheck không được chạy.
- OpenCost: xác nhận chart package 2.5.20, add-on selection và cấu hình Prometheus/ServiceMonitor. Chưa chạy lại Helm template vì Windows Application Control chặn Helm executable có sẵn.

Không tạo tài nguyên cloud, không publish image, không gửi thông báo. Chưa chạy container smoke cục bộ; CI đã có bước kiểm tra lệnh cloud-report trong image.
