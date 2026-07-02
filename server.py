#!/usr/bin/env python3
"""
Playwright MCP Server — Multi-browser + Session Management
Agent kết nối MCP qua stdio, quản lý nhiều browser/tab với session persistence.

Tools:
  - browser_start / browser_stop
  - navigate, screenshot, click, type, wait, scroll
  - get_text, get_url, evaluate
  - wait_for_url, close_page
  - session_save / session_load / session_list
"""

import asyncio
import json
import time
import base64
import logging
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationCapabilities
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool, TextContent, ImageContent, EmbeddedResource,
    CallToolResult
)
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# ─── Config ────────────────────────────────────────────

SESSION_DIR = Path("./sessions")
SESSION_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("playwright-mcp")

# ─── Browser Pool ──────────────────────────────────────

@dataclass
class BrowserSession:
    """Quản lý 1 instance browser + các tab"""
    page_id: str
    browser: Browser
    context: BrowserContext
    page: Page
    created_at: float
    url: str = ""

@dataclass
class BrowserPool:
    """Pool quản lý nhiều browser session"""
    instances: dict[str, BrowserSession] = field(default_factory=dict)
    playwright = None
    _counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"browser_{self._counter}"

    async def start(self, headless: bool = True) -> str:
        """Khởi tạo browser mới"""
        if not self.playwright:
            self.playwright = await async_playwright().start()

        bid = self._next_id()
        browser = await self.playwright.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="vi-VN",
        )
        page = await context.new_page()

        session = BrowserSession(
            page_id=bid,
            browser=browser,
            context=context,
            page=page,
            created_at=time.time(),
        )
        self.instances[bid] = session
        logger.info(f"[Pool] Started browser {bid} (total: {len(self.instances)})")
        return bid

    async def navigate(self, bid: str, url: str) -> dict:
        """Mở URL trong browser"""
        session = self._get(bid)
        await session.page.goto(url, wait_until="networkidle", timeout=30000)
        session.url = session.page.url
        return {
            "browserId": bid,
            "url": session.page.url,
            "title": await session.page.title(),
        }

    async def screenshot(self, bid: str, full_page: bool = False) -> dict:
        """Chụp ảnh màn hình"""
        session = self._get(bid)
        data = await session.page.screenshot(full_page=full_page, type="png")
        return {
            "browserId": bid,
            "base64": base64.b64encode(data).decode(),
            "mimeType": "image/png",
            "url": session.page.url,
        }

    async def click(self, bid: str, selector: str) -> dict:
        await self._get(bid).page.click(selector)
        return {"clicked": selector}

    async def type_text(self, bid: str, selector: str, text: str) -> dict:
        await self._get(bid).page.fill(selector, text)
        return {"typed": selector, "text": text}

    async def wait(self, bid: str, selector: str = None, timeout: int = 5000) -> dict:
        session = self._get(bid)
        if selector:
            await session.page.wait_for_selector(selector, timeout=timeout)
            return {"waited": f"selector '{selector}' appeared"}
        await asyncio.sleep(timeout / 1000)
        return {"waited": f"{timeout}ms"}

    async def get_text(self, bid: str, selector: str) -> dict:
        text = await self._get(bid).page.text_content(selector)
        return {"selector": selector, "text": text}

    async def get_url(self, bid: str) -> dict:
        return {"url": self._get(bid).page.url}

    async def scroll(self, bid: str, direction: str = "down", amount: int = 500) -> dict:
        dir_map = {"up": -1, "down": 1}
        d = dir_map.get(direction, 1)
        await self._get(bid).page.evaluate(f"window.scrollBy(0, {d * amount})")
        return {"scrolled": f"{direction} {amount}px"}

    async def wait_for_url(self, bid: str, pattern: str, timeout: int = 120000) -> dict:
        session = self._get(bid)
        await session.page.wait_for_url(pattern, timeout=timeout)
        return {"url": session.page.url}

    async def evaluate(self, bid: str, script: str) -> dict:
        result = await self._get(bid).page.evaluate(script)
        return {"result": result}

    async def session_save(self, bid: str, session_id: str = None) -> dict:
        """Lưu browser state (cookies, localStorage)"""
        session = self._get(bid)
        sid = session_id or bid
        state = await session.context.storage_state()
        path = SESSION_DIR / f"{sid}.json"
        path.write_text(json.dumps(state))
        logger.info(f"[Session] Saved {sid} → {path}")
        return {"sessionId": sid, "saved": True, "path": str(path)}

    async def session_load(self, bid:str, session_id: str) -> dict:
        """Load browser state từ file"""
        path = SESSION_DIR / f"{session_id}.json"
        if not path.exists():
            return {"sessionId": session_id, "loaded": False, "error": f"Session {session_id} not found"}
        state = json.loads(path.read_text())
        session = self._get(bid)
        await session.context.add_cookies(state.get("cookies", []))
        # Reload để apply cookies
        await session.page.reload()
        logger.info(f"[Session] Loaded {session_id} ← {path}")
        return {"sessionId": session_id, "loaded": True}

    async def session_list(self) -> list[dict]:
        """Liệt kê tất cả session đã lưu"""
        sessions = []
        for f in sorted(SESSION_DIR.glob("*.json")):
            stat = f.stat()
            sessions.append({
                "sessionId": f.stem,
                "size": stat.st_size,
                "createdAt": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stat.st_ctime)),
            })
        return sessions

    async def close_page(self, bid: str):
        await self._get(bid).page.close()

    async def stop(self, bid: str):
        """Dừng browser"""
        session = self.instances.pop(bid, None)
        if session:
            try:
                await session.browser.close()
            except: pass
            logger.info(f"[Pool] Stopped browser {bid} (remaining: {len(self.instances)})")

    async def stop_all(self):
        """Dừng tất cả browser"""
        for bid in list(self.instances.keys()):
            await self.stop(bid)
        if self.playwright:
            await self.playwright.stop()

    async def status(self) -> dict:
        """Trạng thái pool"""
        return {
            "activeBrowsers": len(self.instances),
            "browserIds": list(self.instances.keys()),
            "sessionFiles": [f.stem for f in SESSION_DIR.glob("*.json")],
        }

    def _get(self, bid: str) -> BrowserSession:
        if bid not in self.instances:
            raise ValueError(f"Browser {bid} không tồn tại. Dùng browser_start trước.")
        return self.instances[bid]


# ─── MCP Server ─────────────────────────────────────────

pool = BrowserPool()
server = Server("playwright-mcp")

# ── Tool Definitions ────────────────────────────────

TOOLS = [
    {"name": "browser_start",        "desc": "Khởi tạo browser mới (có thể mở nhiều)", "params": [("headless", "bool", "Ẩn cửa sổ (default: true)")]},
    {"name": "browser_stop",         "desc": "Dừng browser", "params": [("browserId", "str", "ID của browser")]},
    {"name": "browser_status",       "desc": "Trạng thái tất cả browser", "params": []},
    {"name": "navigate",             "desc": "Mở URL", "params": [("browserId", "str", ""), ("url", "str", "URL hoặc domain")]},
    {"name": "screenshot",           "desc": "Chụp màn hình dạng base64 PNG", "params": [("browserId", "str", ""), ("fullPage", "bool", "Chụp toàn trang (default: false)")]},
    {"name": "click",                "desc": "Click vào element", "params": [("browserId", "str", ""), ("selector", "str", "CSS selector hoặc text")]},
    {"name": "type",                 "desc": "Gõ text vào input", "params": [("browserId", "str", ""), ("selector", "str", ""), ("text", "str", "")]},
    {"name": "wait",                 "desc": "Đợi element hoặc timeout", "params": [("browserId", "str", ""), ("selector", "str?2", "CSS selector (optional)"), ("timeout", "int?3", "Timeout ms (default: 5000)")]},
    {"name": "get_text",             "desc": "Lấy text từ element", "params": [("browserId", "str", ""), ("selector", "str", "")]},
    {"name": "get_url",              "desc": "Lấy URL hiện tại", "params": [("browserId", "str", "")]},
    {"name": "scroll",               "desc": "Cuộn trang", "params": [("browserId", "str", ""), ("direction", "str?2", "up/down (default: down)"), ("amount", "int?3", "Số pixel (default: 500)")]},
    {"name": "wait_for_url",         "desc": "Đợi URL thay đổi (dùng cho login redirect)", "params": [("browserId", "str", ""), ("pattern", "str", "URL pattern: **/chat/**"), ("timeout", "int?3", "Timeout ms (default: 120000)")]},
    {"name": "evaluate",             "desc": "Chạy JavaScript tùy ý trên trang", "params": [("browserId", "str", ""), ("script", "str", "JavaScript code")]},
    {"name": "close_page",           "desc": "Đóng tab hiện tại", "params": [("browserId", "str", "")]},
    {"name": "session_save",         "desc": "Lưu session (cookies, localStorage)", "params": [("browserId", "str", ""), ("sessionId", "str?2", "Tên session (default: browserId)")]},
    {"name": "session_load",         "desc": "Nạp session đã lưu", "params": [("browserId", "str", ""), ("sessionId", "str", "")]},
    {"name": "session_list",         "desc": "Liệt kê sessions đã lưu", "params": []},
]

# ── Handle List Tools ───────────────────────────────

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    tools = []
    for t in TOOLS:
        props = {}
        required = []
        for p in t["params"]:
            name_parts = p[0].split("?")
            param_name = name_parts[0]
            type_info = p[1].split("?")[0] if "?" not in p[1] else p[1]
            is_optional = "?" in p[1]
            props[param_name] = {"type": type_info, "description": p[2]}
            if not is_optional and not name_parts[0].endswith("?"):
                required.append(param_name)
        tools.append(Tool(
            name=t["name"],
            description=t["desc"],
            inputSchema={
                "type": "object",
                "properties": props,
                "required": required,
            },
        ))
    return tools

# ── Handle Tool Call ────────────────────────────────

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        # Khởi tạo browser
        if name == "browser_start":
            bid = await pool.start(headless=arguments.get("headless", True))
            return [TextContent(type="text", text=json.dumps({"browserId": bid, "status": "started"}, ensure_ascii=False))]

        # Stop / status
        if name == "browser_stop":
            await pool.stop(arguments["browserId"])
            return [TextContent(type="text", text=json.dumps({"stopped": arguments["browserId"]}))]
        if name == "browser_status":
            s = await pool.status()
            return [TextContent(type="text", text=json.dumps(s, indent=2, ensure_ascii=False))]

        # Browser actions
        bid = arguments.get("browserId", "")
        if name == "navigate":
            r = await pool.navigate(bid, arguments["url"])
        elif name == "screenshot":
            r = await pool.screenshot(bid, arguments.get("fullPage", False))
        elif name == "click":
            r = await pool.click(bid, arguments["selector"])
        elif name == "type":
            r = await pool.type_text(bid, arguments["selector"], arguments["text"])
        elif name == "wait":
            r = await pool.wait(bid, arguments.get("selector"), arguments.get("timeout", 5000))
        elif name == "get_text":
            r = await pool.get_text(bid, arguments["selector"])
        elif name == "get_url":
            r = await pool.get_url(bid)
        elif name == "scroll":
            r = await pool.scroll(bid, arguments.get("direction", "down"), arguments.get("amount", 500))
        elif name == "wait_for_url":
            r = await pool.wait_for_url(bid, arguments["pattern"], arguments.get("timeout", 120000))
        elif name == "evaluate":
            r = await pool.evaluate(bid, arguments["script"])
        elif name == "close_page":
            await pool.close_page(bid)
            r = {"closed": bid}
        elif name == "session_save":
            r = await pool.session_save(bid, arguments.get("sessionId"))
        elif name == "session_load":
            r = await pool.session_load(bid, arguments["sessionId"])
        elif name == "session_list":
            r = {"sessions": await pool.session_list()}
        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

        return [TextContent(type="text", text=json.dumps(r, ensure_ascii=False, indent=2))]

    except Exception as e:
        logger.error(f"[Tool:{name}] {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


# ─── Main ───────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationCapabilities(
                sampling={},
                experimental={},
            ),
            notification_options=NotificationOptions(),
        )

def run():
    """Entry point cho CLI"""
    asyncio.run(main())

if __name__ == "__main__":
    run()
