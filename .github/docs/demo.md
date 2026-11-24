# Demo portfolio trong 5 phút

Demo này dành cho nhà tuyển dụng xem cách tổ chức nền tảng, kiểm thử và xử lý chi phí. Chỉ cần Python 3.11 trở lên; không cần cài package, đăng nhập AWS hay mở cổng mạng. Kết quả dùng dữ liệu tổng hợp, không phải bằng chứng đã triển khai cloud.

## Chuẩn bị và chạy

Clone monorepo theo [quick-start](quick-start.md), rồi chạy từ root bằng PowerShell hoặc Bash:

```text
python scripts/portfolio_demo.py
```

Lệnh in đường dẫn thư mục bằng chứng mới dưới `.scratch/portfolio-demo-<UTC timestamp>`. Mỗi lần chạy có thư mục riêng. Có thể chọn đường dẫn mới bằng `--output-dir`; thư mục đã tồn tại sẽ bị từ chối để giữ nguyên bằng chứng cũ.

| File đầu ra | Dùng để trình bày |
| --- | --- |
| `summary.md` | Thời gian UTC, phiên bản Python, từng lệnh và mã thoát khi lỗi |
| `finops-tests.log` | Kiểm thử dữ liệu thiếu, credit, currency, thông báo và báo cáo |
| `digest-tests.log` | Chỉ chấp nhận bộ digest đầy đủ và đúng source revision |
| `weekly-report.md` | OpenCost $89.47 và CUR $140.00, hiển thị riêng |
| `cloud-report.md` | AWS/GCP/Azure, tổng 43.75 USD trong mỗi tuần |
| `waste-report.md` | Bốn tài nguyên ứng viên, ước tính $27.88/tháng với mức giá minh họa mặc định |

Nếu đã đặt biến môi trường giá waste, chúng vẫn được CLI sử dụng; xóa các override trước khi đối chiếu số mặc định. Script dừng ngay khi một lệnh lỗi, trả mã thoát khác 0 và giữ log. Chỉ trình bày kết quả thành công sau khi đọc `summary.md`.

## Kịch bản trình bày

| Thời gian | Mở gì | Nội dung |
| --- | --- | --- |
| 0:00–0:45 | [Sơ đồ kiến trúc](architecture/overview.md) | Online Boutique là ứng dụng mẫu của Google. Phần đóng góp là hạ tầng, CI/GitOps, policy, FinOps và kiểm chứng. Phân biệt mã nguồn, image và desired state. |
| 0:45–1:30 | Terminal chạy demo và `summary.md` | Cho thấy các lệnh thực sự chạy. Bộ demo hiện chạy 42 test FinOps và 6 test digest; số lượng có thể tăng khi phát triển. Đây là kiểm thử offline. |
| 1:30–2:30 | Hai báo cáo chi phí | Giải thích OpenCost phân bổ theo workload, CUR phản ánh billing và hai nguồn có thể trùng nhau. Không cộng tổng. Mở `finops-toolkit/tests/test_athena.py`, chỉ ra kỳ thiếu ngày phải bị từ chối thay vì coi là chi phí 0. |
| 2:30–3:30 | Root `.github/workflows/ci.yml`, `release.yml` và `digest-tests.log` | Push main chỉ validate/build/scan. Tag `v0.9` yêu cầu main đã validate trước khi publish. Operator review digest và mở PR GitOps; tự động promotion chưa được chuyển sang monorepo. |
| 3:30–4:30 | `frontend-rollout.yaml`, `analysis-template.yaml` và [rollback runbook](runbooks/rollback-thu-cong.md) | Giải thích canary dùng probe `/`, trọng số theo replica gần đúng. Abort không tự sửa desired state trong Git; cần revert PR. Đây là walkthrough cấu hình, chưa phải canary chạy thật. |
| 4:30–5:00 | [Bằng chứng hiện tại](evidence/portfolio-readiness-2026-11-16.md) | Nêu phần đã kiểm chứng, phần chưa chạy, Redis ephemeral và giới hạn chi phí. Lab EKS phải có tài khoản/quyền, đường mạng private và ngân sách phù hợp. |

## Các câu hỏi nên trả lời được

- Tại sao triển khai theo digest thay vì chỉ dùng tag? Bộ digest thiếu service phải xử lý thế nào?
- Tại sao không cộng OpenCost và CUR? Credit âm và ngày thiếu dữ liệu ảnh hưởng báo cáo ra sao?
- Tại sao production sync thủ công? Canary abort khác Git revert ở đâu?
- Downscaler giảm replica có bảo đảm giảm hóa đơn EC2 không?
- Nếu Redis hoặc Prometheus nonprod bị thay Pod, dữ liệu nào có thể mất?

Muốn trình bày checkout thật, phải chạy smoke command đối với storefront đã triển khai theo [runbook](runbooks/khoi-phuc-cluster-tu-git.md). Demo offline không chạy các kiểm thử socket, không provision cluster và không gửi thông báo.
