#!/usr/bin/env python3
"""
Playwright MCP Server — Lightweight REST API (Python 3.9 compatible)
Không cần mcp package, chỉ cần playwright + Python built-in modules.

Deploy trên cPanel: trỏ passenger_wsgi.py tới file này
Chạy local: python server.py --port 8000

Tools: browser_start, navigate, screenshot, click, type, wait, get_text,
       scroll, close_page, session_save/load/list, status
"""

import asyncio, json, base64, time, os, sys
from pathlib import Path

# ─── Browser Pool ──────────────────────────────────

SESSION_DIR = Path("./sessions")
SESSION_DIR.mkdir(exist_ok=True)

class BrowserPool:
    def __init__(self):
        self._playwright = None
        self._instances = {}  # bid -> {browser, context, page}
        self._counter = 0

    async def _ensure_playwright(self):
        if not self._playwright:
            from playwright.async_api import async_playwright
            # Auto-install Chromium if needed
            import subprocess
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    capture_output=True, text=True, timeout=300
                )
            except: pass
            self._playwright = await async_playwright().start()

    async def start(self, headless=True):
        await self._ensure_playwright()
        self._counter += 1
        bid = f"browser_{self._counter}"
        browser = await self._playwright.chromium.launch(headless=headless, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width":1280,"height":720})
        page = await context.new_page()
        self._instances[bid] = {"browser":browser, "context":context, "page":page}
        return bid

    def _get(self, bid): return self._instances[bid]

    async def navigate(self, bid, url):
        s = self._get(bid)
        await s["page"].goto(url, wait_until="load", timeout=30000)
        return {"url": s["page"].url, "title": await s["page"].title()}

    async def screenshot(self, bid):
        s = self._get(bid)
        data = await s["page"].screenshot(type="png")
        return {"base64": base64.b64encode(data).decode(), "mimeType": "image/png"}

    async def click(self, bid, sel):
        await self._get(bid)["page"].click(sel)
        return {"clicked": sel}

    async def type_text(self, bid, sel, txt):
        await self._get(bid)["page"].fill(sel, txt)
        return {"typed": sel, "text": txt}

    async def wait(self, bid, sel=None, timeout=5000):
        s = self._get(bid)
        if sel:
            await s["page"].wait_for_selector(sel, timeout=timeout)
            return {"waited": sel}
        import asyncio; await asyncio.sleep(timeout/1000)
        return {"waited": f"{timeout}ms"}

    async def get_text(self, bid, sel):
        txt = await self._get(bid)["page"].text_content(sel)
        return {"selector": sel, "text": txt}

    async def get_url(self, bid): return {"url": self._get(bid)["page"].url}

    async def scroll(self, bid, dir="down", amt=500):
        d = 1 if dir!="up" else -1
        await self._get(bid)["page"].evaluate(f"window.scrollBy(0,{d*amt})")
        return {"scrolled": f"{dir} {amt}px"}

    async def wait_for_url(self, bid, pat, timeout=120000):
        s = self._get(bid)
        await s["page"].wait_for_url(pat, timeout=timeout)
        return {"url": s["page"].url}

    async def evaluate(self, bid, script):
        r = await self._get(bid)["page"].evaluate(script)
        return {"result": r}

    async def session_save(self, bid, sid=None):
        s = self._get(bid)
        sd = sid or bid
        state = await s["context"].storage_state()
        (SESSION_DIR/f"{sd}.json").write_text(json.dumps(state))
        return {"sessionId": sd, "saved": True}

    async def session_load(self, bid, sid):
        p = SESSION_DIR/f"{sid}.json"
        if not p.exists(): return {"loaded": False, "error": "Not found"}
        state = json.loads(p.read_text())
        await self._get(bid)["context"].add_cookies(state.get("cookies",[]))
        await self._get(bid)["page"].reload()
        return {"sessionId": sid, "loaded": True}

    async def session_list(self):
        ss = []
        for f in sorted(SESSION_DIR.glob("*.json")):
            st = f.stat()
            ss.append({"sessionId":f.stem,"size":st.st_size})
        return ss

    async def close_page(self, bid):
        await self._get(bid)["page"].close()

    async def stop(self, bid):
        s = self._instances.pop(bid, None)
        if s:
            try: await s["browser"].close()
            except: pass

    async def status(self):
        return {"activeBrowsers": len(self._instances), "browserIds": list(self._instances.keys())}

pool = BrowserPool()

# ─── REST API Handler ─────────────────────────────

API_KEY = os.environ.get("MCP_API_KEY", "")

async def handle_tool(action: str, args: dict) -> dict:
    try:
        if action == "browser_start":
            bid = await pool.start(headless=args.get("headless", True))
            return {"browserId": bid, "status": "started"}
        elif action == "browser_stop":
            await pool.stop(args["browserId"])
            return {"stopped": args["browserId"]}
        elif action == "browser_status":
            return await pool.status()

        bid = args.get("browserId", "")
        if action == "navigate":
            return await pool.navigate(bid, args["url"])
        elif action == "screenshot":
            return await pool.screenshot(bid)
        elif action == "click":
            return await pool.click(bid, args["selector"])
        elif action == "type":
            return await pool.type_text(bid, args["selector"], args["text"])
        elif action == "wait":
            return await pool.wait(bid, args.get("selector"), args.get("timeout", 5000))
        elif action == "get_text":
            return await pool.get_text(bid, args["selector"])
        elif action == "get_url":
            return await pool.get_url(bid)
        elif action == "scroll":
            return await pool.scroll(bid, args.get("direction","down"), args.get("amount",500))
        elif action == "wait_for_url":
            return await pool.wait_for_url(bid, args["pattern"], args.get("timeout",120000))
        elif action == "evaluate":
            return await pool.evaluate(bid, args["script"])
        elif action == "close_page":
            await pool.close_page(bid)
            return {"closed": bid}
        elif action == "session_save":
            return await pool.session_save(bid, args.get("sessionId"))
        elif action == "session_load":
            return await pool.session_load(bid, args["sessionId"])
        elif action == "session_list":
            return {"sessions": await pool.session_list()}
        else:
            return {"error": f"Unknown action: {action}"}
    except Exception as e:
        return {"error": str(e)}

# ─── HTTP Handler ────────────────────────────────

import http.server
import urllib.parse

class MCPHandler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        self._json_response(200, {"service":"playwright-mcp","version":"1.0.0","python":sys.version.split()[0]})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Check API key
        if API_KEY:
            auth = self.headers.get("Authorization","")
            key = auth.replace("Bearer ","") if auth.startswith("Bearer ") else ""
            if key != API_KEY:
                return self._json_response(401, {"error": "Unauthorized"})

        # Parse body
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body)
        except:
            return self._json_response(400, {"error": "Invalid JSON"})

        action = data.get("action", "")
        args = data.get("arguments", data.get("args", {}))

        # Run async handler
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(handle_tool(action, args))
        loop.close()

        self._json_response(200, result)

    def _json_response(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


# ─── Main ───────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="0.0.0.0")
    args = p.parse_args()

    port = int(os.environ.get("PORT", args.port))
    host = os.environ.get("HOST", args.host)

    print(f"[MCP] Server @ {host}:{port}")
    print(f"[MCP] Python {sys.version.split()[0]}")
    print(f"[MCP] API Key: {'enabled' if API_KEY else 'DISABLED'}")

    server = http.server.HTTPServer((host, port), MCPHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
