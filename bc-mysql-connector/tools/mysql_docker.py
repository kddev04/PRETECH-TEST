"""Make sure the local MySQL container for the demo is running. Used by start-demo.bat.

Reads MYSQL_* from .env. Creates the container `pretech-mysql` (mysql:8.4) the first time,
starts it if it is stopped, and waits until MySQL answers. Exit code 0 = ready, 1 = not available.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
NAME = "pretech-mysql"
IMAGE = "mysql:8.4"


def sh(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def main() -> int:
    load_dotenv(ROOT / ".env")
    port = os.environ.get("MYSQL_PORT", "3307")
    user = os.environ.get("MYSQL_USER", "bcsync")
    pw = os.environ.get("MYSQL_PASSWORD", "")
    root_pw = os.environ.get("MYSQL_ROOT_PASSWORD", "")
    dbname = os.environ.get("MYSQL_DB", "bc_sync")
    if not pw or not root_pw or "change-me" in (pw, root_pw):
        print("  .env has no MySQL passwords yet. Run setup.bat first.")
        return 1

    try:
        info = sh("info", "--format", "{{.ServerVersion}}", timeout=20)
    except FileNotFoundError:
        print("  Docker is not installed.")
        return 1
    except subprocess.TimeoutExpired:
        info = None
    if not info or info.returncode != 0:
        print("  Docker Desktop is not running. Start it, wait for 'Engine running', then try again.")
        return 1

    state = sh("ps", "-a", "--filter", f"name=^{NAME}$", "--format", "{{.State}}").stdout.strip()
    if not state:
        print(f"  Creating MySQL container {NAME} ({IMAGE}) on 127.0.0.1:{port} ... first time can take a few minutes")
        r = sh("run", "-d", "--name", NAME, "-p", f"127.0.0.1:{port}:3306",
               "-e", f"MYSQL_ROOT_PASSWORD={root_pw}", "-e", f"MYSQL_DATABASE={dbname}",
               "-e", f"MYSQL_USER={user}", "-e", f"MYSQL_PASSWORD={pw}",
               IMAGE, "--character-set-server=utf8mb4", "--collation-server=utf8mb4_0900_ai_ci", timeout=900)
        if r.returncode != 0:
            print("  Could not create the container:", (r.stderr or r.stdout).strip()[:400])
            return 1
    elif state != "running":
        print(f"  Starting MySQL container {NAME} ...")
        r = sh("start", NAME)
        if r.returncode != 0:
            print("  Could not start the container:", (r.stderr or r.stdout).strip()[:400])
            return 1

    print("  Waiting for MySQL to accept connections", end="", flush=True)
    for _ in range(90):
        ping = sh("exec", NAME, "mysqladmin", "ping", "-h127.0.0.1", f"-u{user}", f"-p{pw}", "--silent", timeout=20)
        if ping.returncode == 0:
            # the server answers before user grants are ready on first boot; check a real login too
            probe = sh("exec", NAME, "mysql", f"-u{user}", f"-p{pw}", "-e", "SELECT 1", dbname, timeout=20)
            if probe.returncode == 0:
                print(" ready.")
                return 0
        print(".", end="", flush=True)
        time.sleep(2)
    print("\n  MySQL did not become ready in time. Check Docker Desktop for the pretech-mysql container.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
