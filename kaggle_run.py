"""Kaggle launcher.

Run from the repository root:
    python kaggle_run.py

The process starts FastAPI in the background and prints a public quick-tunnel URL
when cloudflared is available. It intentionally does not block the notebook cell.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.getenv("RECAP_PORT", "8000"))
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


def start_server() -> subprocess.Popen:
    log = (LOG_DIR / "server.log").open("ab")
    env = os.environ.copy()
    env.setdefault("RECAP_HOST", "0.0.0.0")
    env.setdefault("RECAP_PORT", str(PORT))
    return subprocess.Popen(
        [env.get("PYTHON", "python"), "run.py"],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def wait_for_server(timeout: int = 30) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/settings", timeout=2) as response:
                return response.status == 200
        except Exception:
            time.sleep(1)
    return False


def start_tunnel() -> tuple[subprocess.Popen | None, str | None]:
    cloudflared = shutil.which("cloudflared") or str(ROOT / "cloudflared")
    if not Path(cloudflared).exists():
        return None, None
    log_path = LOG_DIR / "tunnel.log"
    log_path.write_text("", encoding="utf-8")
    log = log_path.open("ab")
    proc = subprocess.Popen(
        [cloudflared, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 35
    pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    while time.time() < deadline:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
        match = pattern.search(text)
        if match:
            return proc, match.group(0)
        time.sleep(1)
    return proc, None


if __name__ == "__main__":
    server = start_server()
    if not wait_for_server():
        raise SystemExit("FastAPI failed to start; inspect logs/server.log")
    print(f"LOCAL_URL=http://127.0.0.1:{PORT}")
    tunnel, public_url = start_tunnel()
    if public_url:
        print(f"PUBLIC_URL={public_url}")
        print("Keep the Kaggle session running while using the URL.")
    else:
        print("PUBLIC_URL unavailable. Install/start cloudflared or use local requests.")
    print(f"SERVER_PID={server.pid}")
