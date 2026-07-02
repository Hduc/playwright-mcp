#!/usr/bin/env python3
"""Setup script for Playwright MCP Server
Chạy từ cPanel: Execute Python Script → setup.py
"""

import subprocess
import sys
import os

def run(cmd, timeout=300):
    print(f"> {cmd}")
    try:
        result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=timeout)
        if result.stdout: print(result.stdout.strip())
        if result.stderr: print(result.stderr.strip())
        return result.returncode == 0
    except Exception as e:
        print(f"ERROR: {e}")
        return False

print("=" * 50)
print("Playwright MCP Server — Setup")
print(f"Python: {sys.version}")
print("=" * 50)

# Step 1: Upgrade pip
print("\n[1/3] Upgrade pip...")
run(f"{sys.executable} -m pip install --upgrade pip --quiet")

# Step 2: Install playwright (prefer binary wheel, no compilation)
print("\n[2/3] Install Playwright...")
ok = run(f"{sys.executable} -m pip install --prefer-binary --only-binary :all: playwright")
if not ok:
    print("Trying fallback...")
    run(f"{sys.executable} -m pip install playwright==1.40.0")

# Step 3: Install Chromium browser
print("\n[3/3] Install Chromium (~150MB)...")
import shutil
if shutil.which(f"{sys.executable}"):
    run(f"{sys.executable} -m playwright install chromium --with-deps")
else:
    print("⚠️  Could not find playwright CLI. Run manually: python -m playwright install chromium")

print("\n" + "=" * 50)
print("Setup completed!")
print("=" * 50)
print()
print("To start MCP server:")
print(f"  cd {os.getcwd()}")
print(f"  {sys.executable} server.py --port 8000")
