#!/bin/bash
# Start MCP Server in background
# Chạy từ cPanel: Execute Python Script → chọn start.sh
# Hoặc: bash start.sh

cd /home/yu9jxvq6kp57/browser1-mcp

# Dùng Python từ virtualenv
PYTHON=/home/yu9jxvq6kp57/virtualenv/browser1-mcp/3.11/bin/python3.11_bin

# Kill old server nếu đang chạy
pkill -f "server.py" 2>/dev/null
sleep 1

# Start server in background
nohup $PYTHON server.py --port 8000 > /home/yu9jxvq6kp57/browser1-mcp/server.log 2>&1 &

echo "MCP Server started (PID: $!)"
echo "Check log: tail -f /home/yu9jxvq6kp57/browser1-mcp/server.log"
