# Playwright MCP Server

> Browser automation cho AI Agent qua Model Context Protocol (MCP)

### Cài đặt

```bash
git clone git@github.com:Hduc/playwright-mcp.git
cd playwright-mcp
npm install
npx playwright install chromium
```

### Chạy

```bash
npm start
# MCP Server listening on stdio...
```

### Agent kết nối

Agent cấu hình MCP client:

```json
{
    "mcpServers": {
        "playwright": {
            "command": "node",
            "args": ["/path/to/playwright-mcp/index.js"]
        }
    }
}
```

### Các tool có sẵn

| Tool | Mô tả | Ví dụ |
|---|---|---|
| `initialize` | Khởi động browser | `{ headless: false }` |
| `navigate` | Mở URL trong tab mới | `{ url: "https://zalo.me" }` → `pageId` |
| `screenshot` | Chụp ảnh màn hình (base64) | `{ pageId: "page_xxx" }` → `base64` |
| `click` | Click vào element | `{ pageId, selector: "button" }` |
| `type` | Gõ text | `{ pageId, selector: "input", text: "hello" }` |
| `wait` | Đợi element hoặc timeout | `{ pageId, selector: ".qr", timeout: 10000 }` |
| `get_text` | Lấy text từ element | `{ pageId, selector: "#title" }` |
| `get_url` | Lấy URL hiện tại | `{ pageId }` |
| `scroll` | Cuộn trang | `{ pageId, direction: "down", amount: 500 }` |
| `wait_for_url` | Đợi URL thay đổi (login redirect) | `{ pageId, pattern: "**/chat/**", timeout: 120000 }` |
| `close_page` | Đóng tab | `{ pageId }` |

### Ví dụ: Login Zalo + QR

Agent gửi các lệnh MCP:

```json
// 1. Mở Zalo
{ "method": "tools/call", "params": { "name": "navigate", "arguments": { "url": "https://chat.zalo.me/" } } }
→ { "pageId": "page_12345_abc" }

// 2. Đợi QR
{ "method": "tools/call", "params": { "name": "wait", "arguments": { "pageId": "page_12345_abc", "selector": "canvas", "timeout": 15000 } } }

// 3. Chụp QR
{ "method": "tools/call", "params": { "name": "screenshot", "arguments": { "pageId": "page_12345_abc" } } }
→ { "base64": "iVBORw0KGgo..." } // Gửi QR cho user

// 4. Đợi login thành công (URL đổi sang /chat/)
{ "method": "tools/call", "params": { "name": "wait_for_url", "arguments": { "pageId": "page_12345_abc", "pattern": "**/chat/**", "timeout": 120000 } } }
→ Login thành công!
```

### Kiến trúc

```
┌─────────┐     MCP (stdio)     ┌───────────────┐
│  Agent  │ ←─────────────────→ │ Playwright MCP │
│  (AI)   │                     │    Server      │
└─────────┘                     │  (index.js)    │
                                │       │        │
                                │  Chromium       │
                                │  (Playwright)   │
                                └───────┬─────────┘
                                        │
                                    Web/Zalo
```
