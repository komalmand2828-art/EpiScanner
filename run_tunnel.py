import os
import re
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not url or not key:
    raise RuntimeError("Supabase credentials missing from .env")

supabase = create_client(url, key)

process = subprocess.Popen(
    [
        "/usr/local/bin/cloudflared",
        "tunnel",
        "--no-autoupdate",
        "--url",
        "http://127.0.0.1:8000",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

for line in process.stdout:
    print(line, end="", flush=True)

    match = re.search(
        r"https://[a-z0-9-]+\.trycloudflare\.com",
        line
    )

    if match:
        tunnel_url = match.group(0)

        supabase.table("device_config").upsert(
            {
                "id": 1,
                "tunnel_url": tunnel_url,
            },
            on_conflict="id",
        ).execute()

        print("Tunnel URL published to Supabase:", tunnel_url,
              flush=True)

process.wait()
raise SystemExit(process.returncode)