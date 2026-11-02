"""Local report server (stdlib only, loopback by default)."""

from __future__ import annotations

import http.server
import json
import socketserver
from pathlib import Path
from typing import Optional

INDEX_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ProtectREVERSE reports</title>
<style>body{font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
margin:0;padding:32px;max-width:820px;color:#16181d;background:#f7f7f5}
h1{font-size:20px;letter-spacing:-.01em}a{color:#1f4b8f;text-decoration:none}
li{margin:6px 0}code{background:#e9eaec;padding:1px 5px;border-radius:4px}
.muted{color:#5d6470;font-size:13px}</style></head>
<body><h1>ProtectREVERSE reports</h1>
<p class="muted">Local, read-only listing. Nothing here is uploaded.</p><ul>__ROWS__</ul>
</body></html>"""


class ReportHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: Optional[str] = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def list_directory(self, path):  # noqa: N802 - stdlib signature
        entries = sorted(Path(path).glob("*.html"))
        rows = "".join(
            f'<li><a href="{entry.name}">{entry.name}</a></li>' for entry in entries
        ) or "<li class=\"muted\">No reports yet. Run a scan first.</li>"
        payload = INDEX_HTML.replace("__ROWS__", rows).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        return self.wfile.write(payload)

    def log_message(self, fmt, *args):  # quieter logs
        return


def serve(directory: Path, port: int = 8787, host: str = "127.0.0.1") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    import functools

    handler = functools.partial(ReportHandler, directory=str(directory))
    with socketserver.TCPServer((host, port), handler) as httpd:
        print(f"ProtectREVERSE reports: http://{host}:{port}")
        print(f"Serving {directory} (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":  # pragma: no cover
    from .config import REPORT_DIR

    serve(Path(REPORT_DIR))
