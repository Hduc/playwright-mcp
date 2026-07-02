# Playwright MCP Server 🖥️🐍

> Browser automation cho AI Agent qua Model Context Protocol (MCP) — Python edition
>
> Multi-browser, session persistence, async — Agent kết nối qua stdio

---

### Cài đặt

```bash
git clone git@github.com:Hduc/playwright-mcp.git
cd playwright-mcp

# Tạo môi trường ảo + cài dependencies
uv venv && uv pip install -e .

# Cài Chromium (chỉ cần chạy 1 lần, ~150MB)
python -m playwright install chromium
```

---

### Chạy

```bash
python server.py
# MCP Server listening on stdio...
```

---

### Agent kết nối

Agent cấu hình MCP client:

```json
{
    "mcpServers": {
        "playwright": {
            "command": "python",
            "args": ["/path/to/playwright-mcp/server.py"]
        }
    }
}
```

Hoặc dùng `uv`:

```json
{
    "mcpServers": {
        "playwright": {
            "command": "uv",
            "args": ["run", "python", "/path/to/playwright-mcp/server.py"]
        }
    }
}
```

---

### Tools (18 công cụ)

| Tool | Mô tả | Tham số |
|---|---|---|
| `browser_start` | Khởi tạo browser mới (mở nhiều) | `headless` (bool) |
| `browser_stop` | Dừng browser | `browserId` |
| `browser_status` | Xem trạng thái tất cả browser | — |
| `navigate` | Mở URL | `browserId`, `url` |
| `screenshot` | Chụp màn hình → base64 PNG | `browserId`, `fullPage?` |
| `click` | Click vào element | `browserId`, `selector` |
| `type` | Gõ text vào input | `browserId`, `selector`, `text` |
| `wait` | Đợi element hoặc N ms | `browserId`, `selector?`, `timeout?` |
| `scroll` | Cuộn trang | `browserId`, `direction?`, `amount?` |
| `get_text` | Lấy text từ element | `browserId`, `selector` |
| `get_url` | Lấy URL hiện tại | `browserId` |
| `evaluate` | Chạy JavaScript trên trang | `browserId`, `script` |
| `wait_for_url` | Đợi URL thay đổi (login redirect) | `browserId`, `pattern`, `timeout?` |
| `close_page` | Đóng tab | `browserId` |
| `session_save` | Lưu cookies + localStorage | `browserId`, `sessionId?` |
| `session_load` | Nạp session đã lưu | `browserId`, `sessionId` |
| `session_list` | Liệt kê sessions | — |

> `?` = optional

---

### Ví dụ: Agent login Zalo + lấy QR

```json
// 1. Mở browser
{"method": "tools/call", "params": {"name": "browser_start", "arguments": {"headless": true}}}
→ {"browserId": "browser_1"}

// 2. Mở Zalo
{"method": "tools/call", "params": {"name": "navigate", "arguments": {"browserId": "browser_1", "url": "https://chat.zalo.me/"}}}
→ {"url": "https://chat.zalo.me/", "title": "Zalo Web"}

// 3. Đợi QR hiện
{"method": "tools/call", "params": {"name": "wait", "arguments": {"browserId": "browser_1", "selector": "canvas", "timeout": 15000}}}

// 4. Chụp QR gửi user
{"method": "tools/call", "params": {"name": "screenshot", "arguments": {"browserId": "browser_1"}}}
→ {"base64": "iVBORw0KGgo..."}

// 5. Đợi login thành công
{"method": "tools/call", "params": {"name": "wait_for_url", "arguments": {"browserId": "browser_1", "pattern": "**/chat/**", "timeout": 120000}}}
→ Login OK!

// 6. Lưu session
{"method": "tools/call", "params": {"name": "session_save", "arguments": {"browserId": "browser_1", "sessionId": "zalo_demo"}}}
→ {"saved": true}
```

---

### Ví dụ: Mở nhiều browser cùng lúc

```json
// Browser 1 — Zalo
{"method": "tools/call", "params": {"name": "browser_start", "arguments": {}}}
→ {"browserId": "browser_1"}

// Browser 2 — Facebook
{"method": "tools/call", "params": {"name": "browser_start", "arguments": {}}}
→ {"browserId": "browser_2"}

// Browser 3 — WhatsApp
{"method": "tools/call", "params": {"name": "browser_start", "arguments": {}}}
→ {"browserId": "browser_3"}

// Mỗi browser độc lập, không ảnh hưởng nhau
```

---

### Kiến trúc

```
┌─────────┐     MCP (stdio)     ┌───────────────────┐
│  Agent  │ ←─────────────────→ │ Playwright MCP     │
│  (AI)   │                     │ Server (Python)    │
└─────────┘                     │                    │
                                │ ┌────────────────┐ │
                                │ │ Browser Pool   │ │
                                │ │ ├ browser_1 →  │ │
                                │ │ ├ browser_2 →  │ │
                                │ │ └ browser_3 →  │ │
                                │ └────────────────┘ │
                                │      ↓              │
                                │  Playwright +       │
                                │  Chromium instances │
                                └─────────────────────┘
                                        │
                                    Web/Zalo
                                /sessions/*.json
                                (session persistence)
```

---

### Yêu cầu hệ thống

- Python >= 3.11
- `uv` (pip installer nhanh)
- Chromium browser (~150MB, tự cài qua `playwright install`)

### Phát triển

```bash
uv pip install -e ".[dev]"
pytest
```

### License

MIT
