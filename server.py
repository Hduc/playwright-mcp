#!/usr/bin/env python3
"""
Playwright MCP Server — Multi-browser + Session Management
Hỗ trợ 2 transport: stdio (local) + SSE HTTP (remote)
Chạy:
  python server.py --transport sse --port 8000 --api-key YOUR_KEY
  python server.py --transport stdio

API Key: --api-key flag hoặc env MCP_API_KEY
"""

import asyncio, json, time, base64, logging, os, sys, argparse
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

SESSION_DIR = Path("./sessions")
SESSION_DIR.mkdir(exist_ok=True)
API_KEY = os.environ.get("MCP_API_KEY", "")
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("playwright-mcp")

# ======= Browser Pool =======

@dataclass
class BrowserSession:
    page_id: str; browser: Browser; context: BrowserContext; page: Page
    created_at: float; url: str = ""

@dataclass
class BrowserPool:
    instances: dict[str, BrowserSession] = field(default_factory=dict)
    playwright = None; _counter: int = 0
    def _next_id(self) -> str: self._counter += 1; return f"browser_{self._counter}"
    async def start(self, headless: bool = True) -> str:
        if not self.playwright: self.playwright = await async_playwright().start()
        bid = self._next_id()
        browser = await self.playwright.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(viewport={"width":1280,"height":720}, locale="vi-VN")
        page = await context.new_page()
        self.instances[bid] = BrowserSession(page_id=bid, browser=browser, context=context, page=page, created_at=time.time())
        logger.info(f"[Pool] Started {bid} (total:{len(self.instances)})")
        return bid
    async def navigate(self, bid, url):
        s = self._get(bid); await s.page.goto(url, wait_until="networkidle", timeout=30000)
        s.url = s.page.url; return {"browserId":bid, "url":s.page.url, "title":await s.page.title()}
    async def screenshot(self, bid, full_page=False):
        s = self._get(bid); data = await s.page.screenshot(full_page=full_page, type="png")
        return {"browserId":bid, "base64":base64.b64encode(data).decode(), "mimeType":"image/png", "url":s.page.url}
    async def click(self, bid, sel): await self._get(bid).page.click(sel); return {"clicked":sel}
    async def type_text(self, bid, sel, txt): await self._get(bid).page.fill(sel, txt); return {"typed":sel,"text":txt}
    async def wait(self, bid, sel=None, timeout=5000):
        s = self._get(bid)
        if sel: await s.page.wait_for_selector(sel, timeout=timeout); return {"waited":f"selector \"{sel}\""}
        await asyncio.sleep(timeout/1000); return {"waited":f"{timeout}ms"}
    async def get_text(self, bid, sel): return {"selector":sel, "text":await self._get(bid).page.text_content(sel)}
    async def get_url(self, bid): return {"url":self._get(bid).page.url}
    async def scroll(self, bid, dir="down", amt=500):
        d = 1 if dir!="up" else -1; await self._get(bid).page.evaluate(f"window.scrollBy(0,{d*amt})"); return {"scrolled":f"{dir} {amt}px"}
    async def wait_for_url(self, bid, pat, timeout=120000):
        s = self._get(bid); await s.page.wait_for_url(pat, timeout=timeout); return {"url":s.page.url}
    async def evaluate(self, bid, script): return {"result":await self._get(bid).page.evaluate(script)}
    async def session_save(self, bid, sid=None):
        s = self._get(bid); sd = sid or bid
        state = await s.context.storage_state(); (SESSION_DIR/f"{sd}.json").write_text(json.dumps(state))
        return {"sessionId":sd,"saved":True}
    async def session_load(self, bid, sid):
        p = SESSION_DIR/f"{sid}.json"
        if not p.exists(): return {"loaded":False,"error":"Not found"}
        state = json.loads(p.read_text())
        s = self._get(bid); await s.context.add_cookies(state.get("cookies",[])); await s.page.reload()
        return {"sessionId":sid,"loaded":True}
    async def session_list(self):
        ss = []
        for f in sorted(SESSION_DIR.glob("*.json")):
            st = f.stat(); ss.append({"sessionId":f.stem,"size":st.st_size,"createdAt":time.strftime("%Y-%m-%d %H:%M:%S",time.gmtime(st.st_ctime))})
        return ss
    async def close_page(self, bid): await self._get(bid).page.close()
    async def stop(self, bid):
        s = self.instances.pop(bid,None)
        if s:
            try: await s.browser.close()
            except: pass
            logger.info(f"[Pool] Stopped {bid}")
    async def stop_all(self):
        for bid in list(self.instances.keys()): await self.stop(bid)
        if self.playwright: await self.playwright.stop()
    async def status(self): return {"activeBrowsers":len(self.instances),"browserIds":list(self.instances.keys()),"sessionFiles":[f.stem for f in SESSION_DIR.glob("*.json")]}
    def _get(self, bid):
        if bid not in self.instances: raise ValueError(f"Browser {bid} không tồn tại")
        return self.instances[bid]

pool = BrowserPool()

# ======= MCP Server =======

def create_mcp_server(api_key=""):
    from mcp.server import Server
    from mcp.types import Tool, TextContent

    server = Server("playwright-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(name="browser_start", description="Khởi tạo browser mới", inputSchema={"type":"object","properties":{"headless":{"type":"boolean","description":"Default: true"}}}),
            Tool(name="browser_stop", description="Dừng browser", inputSchema={"type":"object","properties":{"browserId":{"type":"string"}},"required":["browserId"]}),
            Tool(name="browser_status", description="Trạng thái pool", inputSchema={"type":"object","properties":{}}),
            Tool(name="navigate", description="Mở URL", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"url":{"type":"string"}},"required":["browserId","url"]}),
            Tool(name="screenshot", description="Chụp màn hình → base64", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"fullPage":{"type":"boolean"}},"required":["browserId"]}),
            Tool(name="click", description="Click element", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"selector":{"type":"string"}},"required":["browserId","selector"]}),
            Tool(name="type", description="Gõ text", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"selector":{"type":"string"},"text":{"type":"string"}},"required":["browserId","selector","text"]}),
            Tool(name="wait", description="Đợi element/ms", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"selector":{"type":"string"},"timeout":{"type":"integer","description":"ms (default:5000)"}},"required":["browserId"]}),
            Tool(name="get_text", description="Lấy text", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"selector":{"type":"string"}},"required":["browserId","selector"]}),
            Tool(name="get_url", description="Lấy URL", inputSchema={"type":"object","properties":{"browserId":{"type":"string"}},"required":["browserId"]}),
            Tool(name="scroll", description="Cuộn trang", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"direction":{"type":"string"},"amount":{"type":"integer"}},"required":["browserId"]}),
            Tool(name="wait_for_url", description="Đợi URL thay đổi (login redirect)", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"pattern":{"type":"string"},"timeout":{"type":"integer"}},"required":["browserId","pattern"]}),
            Tool(name="evaluate", description="Chạy JavaScript", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"script":{"type":"string"}},"required":["browserId","script"]}),
            Tool(name="close_page", description="Đóng tab", inputSchema={"type":"object","properties":{"browserId":{"type":"string"}},"required":["browserId"]}),
            Tool(name="session_save", description="Lưu session", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"sessionId":{"type":"string"}},"required":["browserId"]}),
            Tool(name="session_load", description="Nạp session", inputSchema={"type":"object","properties":{"browserId":{"type":"string"},"sessionId":{"type":"string"}},"required":["browserId","sessionId"]}),
            Tool(name="session_list", description="DS sessions", inputSchema={"type":"object","properties":{}}),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            if name == "browser_start":
                bid = await pool.start(headless=arguments.get("headless", True))
                return [TextContent(type="text", text=json.dumps({"browserId":bid,"status":"started"},ensure_ascii=False))]
            elif name == "browser_stop":
                await pool.stop(arguments["browserId"])
                return [TextContent(type="text", text=json.dumps({"stopped":arguments["browserId"]}))]
            elif name == "browser_status":
                return [TextContent(type="text", text=json.dumps(await pool.status(),indent=2,ensure_ascii=False))]
            bid = arguments.get("browserId","")
            if   name == "navigate":     r = await pool.navigate(bid, arguments["url"])
            elif name == "screenshot":    r = await pool.screenshot(bid, arguments.get("fullPage",False))
            elif name == "click":         r = await pool.click(bid, arguments["selector"])
            elif name == "type":          r = await pool.type_text(bid, arguments["selector"], arguments["text"])
            elif name == "wait":          r = await pool.wait(bid, arguments.get("selector"), arguments.get("timeout",5000))
            elif name == "get_text":      r = await pool.get_text(bid, arguments["selector"])
            elif name == "get_url":       r = await pool.get_url(bid)
            elif name == "scroll":        r = await pool.scroll(bid, arguments.get("direction","down"), arguments.get("amount",500))
            elif name == "wait_for_url":   r = await pool.wait_for_url(bid, arguments["pattern"], arguments.get("timeout",120000))
            elif name == "evaluate":      r = await pool.evaluate(bid, arguments["script"])
            elif name == "close_page":    await pool.close_page(bid); r = {"closed":bid}
            elif name == "session_save":   r = await pool.session_save(bid, arguments.get("sessionId"))
            elif name == "session_load":   r = await pool.session_load(bid, arguments["sessionId"])
            elif name == "session_list":    r = {"sessions": await pool.session_list()}
            else: r = {"error":f"Unknown: {name}"}
            return [TextContent(type="text", text=json.dumps(r,ensure_ascii=False,indent=2))]
        except Exception as e:
            logger.error(f"[{name}] {e}")
            return [TextContent(type="text", text=json.dumps({"error":str(e)},ensure_ascii=False))]

    return server

async def ensure_chromium_installed():
    """Tự động cài Chromium nếu chưa có — không cần chạy lệnh riêng"""
    import subprocess
    from playwright.sync_api import sync_playwright
    
    def _install():
        try:
            with sync_playwright() as p:
                p.chromium.launch()
            logger.info("[Init] Chromium already installed ✅")
        except Exception:
            logger.info("[Init] Installing Chromium (~150MB)...")
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                logger.info("[Init] Chromium installed ✅")
            else:
                logger.error(f"[Init] Chromium install failed: {result.stderr}")
    await asyncio.get_event_loop().run_in_executor(None, _install)


# ======= stdio Transport =======

async def run_stdio(api_key=""):
    await ensure_chromium_installed()  # Auto-install
    from mcp.server.stdio import stdio_server
    server = create_mcp_server(api_key)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

# ======= SSE Transport =======

async def run_sse(host="0.0.0.0", port=8000, api_key=""):
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount
    from starlette.responses import JSONResponse
    from starlette.middleware import Middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    import uvicorn

    _key = api_key

    class ApiKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.url.path in ("/", "/health"): return await call_next(request)
            if not _key: return await call_next(request)
            auth = request.headers.get("Authorization","")
            key = auth.replace("Bearer ","") if auth.startswith("Bearer ") else ""
            if key != _key:
                return JSONResponse({"error":"Unauthorized — invalid or missing API key"}, status_code=401)
            return await call_next(request)

    async def lifespan(app):
        await ensure_chromium_installed()  # Auto-install Chromium
        logger.info(f"[SSE] Server @ {host}:{port} (API key: {'✅' if _key else '❌ DISABLED'})")
        yield
        await pool.stop_all()

    async def home(request):
        return JSONResponse({
            "service":"playwright-mcp", "version":"1.0.0", "transport":"sse",
            "endpoints":{ "mcp":"/mcp/sse", "health":"/health", "status":"/status" },
            "apiKeyRequired": bool(_key),
            "auth": "Bearer <api_key> in Authorization header",
            "docs":"https://github.com/Hduc/playwright-mcp",
        })

    async def health(request): return JSONResponse({"status":"ok"})
    async def status_api(request): return JSONResponse(await pool.status())

    def create_sse_app():
        sse = SseServerTransport("/messages")
        server = create_mcp_server(_key)
        async def handle_sse(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await server.run(streams[0], streams[1], server.create_initialization_options())
        from starlette.applications import Starlette as SubApp
        return SubApp(routes=[Route("/sse", endpoint=handle_sse)])

    app = Starlette(
        lifespan=lifespan,
        middleware=[Middleware(ApiKeyMiddleware)],
        routes=[
            Route("/", endpoint=home),
            Route("/health", endpoint=health),
            Route("/status", endpoint=status_api),
            Mount("/mcp", app=create_sse_app()),
        ],
    )

    cfg = uvicorn.Config(app, host=host, port=port, log_level="info")
    await uvicorn.Server(cfg).serve()

# ======= CLI =======

def main():
    p = argparse.ArgumentParser(description="Playwright MCP Server")
    p.add_argument("--transport", choices=["stdio","sse"], default="sse")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--api-key", default="", help="API key (or set MCP_API_KEY env)")
    args = p.parse_args()
    key = args.api_key or API_KEY
    if args.transport == "stdio":
        asyncio.run(run_stdio(key))
    else:
        if not key: logger.warning("⚠️  No MCP_API_KEY — server is OPEN!")
        asyncio.run(run_sse(host=args.host, port=args.port, api_key=key))

if __name__ == "__main__":
    main()
