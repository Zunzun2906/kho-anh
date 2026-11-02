# Kho ảnh bách khoa toàn thư tự sinh bằng AI (BT-03)

| Thư mục | Chạy trên VM | Lệnh |
|---|---|---|
| core/    | VM lõi (Postgres, Redis, MinIO) | cp .env.example .env && nano .env && docker compose up -d |
| monitor/ | VM giám sát (ntfy, Uptime Kuma, Beszel hub) | như trên |
| monitor/agent/ | MỌI VM (Beszel agent) | dán KEY từ hub, docker compose up -d |
| web/     | VM web | cp .env.example .env && nano .env && docker compose up -d --build |
| planner/ | VM planner | như trên |
| worker/  | MỌI VM | docker compose up -d --build ai1   (RAM >= 12GB: bỏ "ai1" để chạy cả 2 AI) |

Thứ tự: core -> worker -> planner -> web -> monitor.
Mỗi VM chỉ chạy thư mục của mình; mỗi VM tự tạo file .env (không đưa lên Git).
