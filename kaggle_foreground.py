"""Kaggle launcher with a self-restarting Cloudflare quick tunnel.

Keep the notebook cell running. If a quick tunnel drops, this process starts a
new tunnel and prints its new URL instead of leaving a dead URL on screen.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.getenv("RECAP_PORT", "8000"))
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
CLOUDFLARED = ROOT / "cloudflared"


def ensure_cloudflared() -> None:
    if CLOUDFLARED.exists():
        return
    url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    print("Downloading cloudflared...", flush=True)
    urllib.request.urlretrieve(url, CLOUDFLARED)
    CLOUDFLARED.chmod(CLOUDFLARED.stat().st_mode | stat.S_IEXEC)


def server_ready() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/settings", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def start_server() -> None:
    if server_ready():
        print(f"FastAPI already running: http://127.0.0.1:{PORT}", flush=True)
        return
    log = (LOG_DIR / "server_foreground.log").open("ab")
    env = os.environ.copy()
    env["RECAP_HOST"] = "0.0.0.0"
    env["RECAP_PORT"] = str(PORT)
    subprocess.Popen(
        [sys.executable, "run.py"], cwd=ROOT, env=env,
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 45
    while time.time() < deadline:
        if server_ready():
            print(f"FastAPI ready: http://127.0.0.1:{PORT}", flush=True)
            return
        time.sleep(1)
    raise RuntimeError("FastAPI did not start. Check logs/server_foreground.log")


def run_tunnel_forever() -> None:
    ensure_cloudflared()
    print("Cloudflare tunnel supervisor started.", flush=True)
    print("URL ပျက်သွားရင် URL အသစ်ထွက်တဲ့အထိ ဒီ cell ကို မရပ်ပါနှင့်။", flush=True)
    while True:
        log_path = LOG_DIR / "cloudflared.log"
        with log_path.open("ab") as log:
            proc = subprocess.Popen(
                [str(CLOUDFLARED), "tunnel", "--no-autoupdate", "--protocol", "http2",
                 "--url", f"http://127.0.0.1:{PORT}"],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, start_new_session=True,
            )
            print("Starting a fresh quick tunnel...", flush=True)
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    print(line.rstrip(), flush=True)
                    log.write(line.encode("utf-8", errors="replace"))
                    log.flush()
            finally:
                proc.wait()
        print("Tunnel stopped. Retrying in 3 seconds...", flush=True)
        time.sleep(3)


if __name__ == "__main__":
    start_server()
    run_tunnel_forever()
