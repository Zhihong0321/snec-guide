"""Start SNEC 2026 Guide web app."""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import web.env  # noqa: F401 — load .env before uvicorn imports web.main


def ensure_deps() -> None:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        print("Installing dependencies (first run only)...", flush=True)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements-web.txt")]
        )


def pick_port(preferred: int, tries: int = 10) -> int:
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def _open_browser(port: int) -> None:
    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{port}/enrich")


if __name__ == "__main__":
    ensure_deps()
    import uvicorn

    preferred = int(os.environ.get("PORT", "8080"))
    port = pick_port(preferred)
    reload = os.environ.get("RELOAD", "").lower() in ("1", "true", "yes")
    url = f"http://127.0.0.1:{port}/"

    if port != preferred:
        print(f"Port {preferred} busy — using {port} instead.", flush=True)

    print("", flush=True)
    print("  SNEC 2026 Guide", flush=True)
    print(f"  {url}", flush=True)
    print("  Leave this window open. Close it to stop the app.", flush=True)
    print("", flush=True)

    if os.environ.get("NO_BROWSER") != "1":
        threading.Thread(target=_open_browser, args=(port,), daemon=True).start()

    uvicorn.run(
        "web.main:app",
        host="127.0.0.1",
        port=port,
        reload=reload,
        reload_dirs=[str(ROOT)] if reload else None,
    )
