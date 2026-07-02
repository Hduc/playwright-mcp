#!/usr/bin/env python3
"""Start MCP Server — chạy từ cPanel: Execute Python Script → run.py"""

import subprocess, os, signal

BASE = "/home/yu9jxvq6kp57/browser1-mcp"
PYTHON = f"{BASE}/../virtualenv/browser1-mcp/3.11/bin/python3.11_bin"

try:
    # Kill old process
    try:
        with open(f"{BASE}/server.pid") as f:
            old_pid = int(f.read().strip())
            os.kill(old_pid, signal.SIGTERM)
            print(f"Stopped old server (PID: {old_pid})")
    except: pass

    # Start server
    print("Starting MCP server...")
    with open(f"{BASE}/server.log", "w") as log:
        proc = subprocess.Popen(
            [PYTHON, f"{BASE}/server.py", "--port", "8000"],
            stdout=log, stderr=log,
            cwd=BASE,
            start_new_session=True,
        )
        # Save PID
        with open(f"{BASE}/server.pid", "w") as pf:
            pf.write(str(proc.pid))
        print(f"MCP Server started (PID: {proc.pid})")
        print(f"Check: tail -f {BASE}/server.log")

except Exception as e:
    print(f"ERROR: {e}")
