from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StaticDashboardHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "newYJTStatic/1.0"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        super().end_headers()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the newYJT dashboard and runtime files.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    handler = partial(StaticDashboardHandler, directory=str(ROOT))
    with ThreadingHTTPServer((args.host, args.port), handler) as httpd:
        httpd.daemon_threads = True
        print(f"[static-http] serving {ROOT} on http://{args.host}:{args.port}", flush=True)
        httpd.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
