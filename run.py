#!/usr/bin/env python3
"""Start MCP Server — chạy từ cPanel Execute Python Script"""

import subprocess, os

PYTHON = "/home/yu9jxvq6kp57/virtualenv/browser1-mcp/3.11/bin/python3.11_bin"
SCRIPT = "/home/yu9jxvq6kp57/browser1-mcp/server.py"
LOGFILE = "/home/yu9jxvq6kp57/browser1-mcp/server.log"

# Kill old
print("Stopping old server...")
subprocess.run(["pkill", "-f", "server.py"], capture_output=True)

# Start new
print("Starting MCP server...")
with open(LOGFILE, "w") as log:
    proc = subprocess.Popen(
        [PYTHON, SCRIPT, "--port", "8000"],
        stdout=log, stderr=log,
        start_new_session=True,
    )
    print(f"✅ MCP Server started (PID: {proc.pid})")
    print(f"Log: tail -f {LOGFILE}")
