# Playwright MCP Server 🖥️🐳

> Browser automation cho AI Agent — Node.js + Docker
>
> Multi-browser pool, session persistence, REST API

---

### Deploy

```bash
git clone git@github.com:Hduc/playwright-mcp.git
cd playwright-mcp

# Build + run
docker build -t playwright-mcp .
docker run -d --name mcp -p 8000:8000 playwright-mcp
```

### Chạy có API key

```bash
docker run -d --name mcp -p 8000:8000 \
  -e MCP_API_KEY=*** \
  playwright-mcp
```

---

### Kiểm tra

```bash
curl http://localhost:8000/
# → {"service":"playwright-mcp","version":"2.0.0","runtime":"node.js"}

# Có API key
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer *** \
  -d '{"action":"browser_status"}'
# → {"activeBrowsers":0,"browserIds":[]}
```

---

### Tools (17 công cụ)

Gọi qua `POST /` với body `{"action": "...", "arguments": {...}}`

| Tool | Mô tả | Tham số |
|---|---|---|
| `browser_start` | Mở browser mới | `headless?` |
| `browser_stop` | Dừng browser | `browserId` |
| `browser_status` | Trạng thái pool | — |
| `navigate` | Mở URL | `browserId`, `url` |
| `screenshot` | Chụp màn hình → base64 | `browserId` |
| `click` | Click element | `browserId`, `selector` |
| `type` | Gõ text | `browserId`, `selector`, `text` |
| `wait` | Đợi selector/ms | `browserId`, `selector?`, `timeout?` |
| `scroll` | Cuộn trang | `browserId`, `direction?`, `amount?` |
| `get_text` | Lấy text | `browserId`, `selector` |
| `get_url` | Lấy URL | `browserId` |
| `evaluate` | Chạy JavaScript | `browserId`, `script` |
| `wait_for_url` | Đợi URL (login) | `browserId`, `pattern`, `timeout?` |
| `close_page` | Đóng tab | `browserId` |
| `session_save` | Lưu cookies | `browserId`, `sessionId?` |
| `session_load` | Nạp cookies | `browserId`, `sessionId` |
| `session_list` | DS sessions | — |

---

### Ví dụ: Login Zalo QR

```bash
# 1. Mở browser
curl -X POST http://localhost:8000/ \
  -H "Authorization: Bearer *** \
  -d '{"action":"browser_start"}'
→ {"browserId":"browser_1"}

# 2. Mở Zalo
curl -X POST http://localhost:8000/ \
  -H "Authorization: Bearer *** \
  -d '{"action":"navigate","arguments":{"browserId":"browser_1","url":"https://chat.zalo.me/"}}'

# 3. Đợi QR + chụp
curl -X POST http://localhost:8000/ \
  -H "Authorization: Bearer *** \
  -d '{"action":"wait","arguments":{"browserId":"browser_1","selector":"canvas","timeout":15000}}'

curl -X POST http://localhost:8000/ \
  -H "Authorization: Bearer *** \
  -d '{"action":"screenshot","arguments":{"browserId":"browser_1"}}'
→ {"base64":"iVBORw0KGgo..."}

# 4. Đợi login (URL đổi sang /chat/)
curl -X POST http://localhost:8000/ \
  -H "Authorization: Bearer *** \
  -d '{"action":"wait_for_url","arguments":{"browserId":"browser_1","pattern":"**/chat/**","timeout":120000}}'

# 5. Lưu session
curl -X POST http://localhost:8000/ \
  -H "Authorization: Bearer *** \
  -d '{"action":"session_save","arguments":{"browserId":"browser_1","sessionId":"zalo_main"}}'
```

---

### Kiến trúc

```
┌─────────┐   REST API    ┌───────────────────────┐
│  Agent  │ ───POST─────→ │ Playwright MCP Server  │
│  (AI)   │ ←──JSON────── │ (Node.js + Docker)    │
└─────────┘               │                       │
                          │  ┌─────────────────┐  │
                          │  │  Browser Pool   │  │
                          │  │  ├ browser_1    │  │
                          │  │  ├ browser_2    │  │
                          │  │  └ browser_N    │  │
                          │  └─────────────────┘  │
                          │         ↓             │
                          │  Chromium instances   │
                          └───────────────────────┘
                                   │
                               Web/Zalo
                          /app/sessions/
```

### Yêu cầu

- **Docker** (không cần cài gì khác)
- Port 8000

### License

MIT
