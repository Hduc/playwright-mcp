# passenger_wsgi.py — cPanel entry point
# MCP Server cần chạy như process riêng, không qua Passenger.
# Trên cPanel: Setup Python App → Command: python server.py --port 8000
# Passenger chỉ để hiển thị status page.

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

def application(environ, start_response):
    status = '200 OK'
    headers = [('Content-type', 'text/plain; charset=utf-8')]
    start_response(status, headers)
    return [b'Playwright MCP Server\n\n'
            b'Cai dat: pip install -r requirements.txt\n'
            b'Chay: python server.py --port 8000\n'
            b'API: POST / {\"action\":\"browser_start\",\"arguments\":{}}']
