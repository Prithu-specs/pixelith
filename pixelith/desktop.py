# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. See LICENSE.
"""Native-window launcher used by the Windows, macOS and Linux beta builds."""
from __future__ import annotations

import argparse
import json
import socket
import threading
import time
import urllib.request

from pixelith import __version__
from pixelith.compat import summary


def free_port(preferred: int = 8420) -> int:
    """Use the normal port when available, otherwise ask the OS for one."""
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return int(sock.getsockname()[1])
    raise RuntimeError("could not allocate a local port")


def wait_until_ready(url: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # server is expected to refuse early probes
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"Pixelith did not start: {last_error}")


def diagnostic() -> dict:
    return {"app": "Pixelith", "version": __version__, **summary()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pixelith desktop beta")
    parser.add_argument("--port", type=int, default=8420)
    parser.add_argument("--lan", action="store_true", help="also allow mobile clients")
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args(argv)
    if args.diagnose:
        import sys
        if sys.stdout is not None:
            print(json.dumps(diagnostic(), sort_keys=True))
        return 0

    import uvicorn
    from pixelith.server import app

    port = free_port(args.port)
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    worker = threading.Thread(target=server.run, name="pixelith-server", daemon=True)
    worker.start()
    try:
        wait_until_ready(url)
        import webview

        webview.create_window(
            f"Pixelith {__version__}", url, width=1320, height=860,
            min_size=(760, 600), text_select=True,
        )
        webview.start(debug=False)
    finally:
        server.should_exit = True
        worker.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
