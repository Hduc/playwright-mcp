# passenger_wsgi.py — cPanel Phusion Passenger entry point
# Phusion Passenger will load this file to start the app
import sys
import os

# Add project dir to path
sys.path.insert(0, os.path.dirname(__file__))

# Set default transport to SSE
os.environ.setdefault("MCP_TRANSPORT", "sse")
os.environ.setdefault("MCP_PORT", os.environ.get("PORT", "8000"))

# Import server and run
from server import main

# Passenger expects a WSGI app, but MCP uses ASGI/SSE
# We provide a minimal WSGI wrapper that starts the MCP server in a thread
import threading
import asyncio

def start_mcp():
    asyncio.run(main())

# Start MCP in background thread
t = threading.Thread(target=start_mcp, daemon=True)
t.start()

# Minimal WSGI app for Passenger
def application(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/plain; charset=utf-8')]
    start_response(status, headers)
    return [b'MCP Server is running. Connect via SSE at /mcp/sse']
