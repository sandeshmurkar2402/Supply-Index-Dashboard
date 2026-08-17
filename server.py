#!/usr/bin/env python3
"""Local dashboard server with on-demand data refresh.
Usage: python server.py [port]   (default port: 8080)
"""
import json
import os
import subprocess
import sys
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))

ROOT = os.path.dirname(os.path.abspath(__file__))


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/refresh":
            self._handle_refresh()
        elif path == "/api/sheets":
            self._handle_sheets()
        elif path == "/api/auth/session":
            self._json_response(200, json.dumps({"user": None}).encode())
        else:
            super().do_GET()

    def _handle_sheets(self):
        """Mocks the portal's same-origin /api/sheets proxy for local preview of
        supply_index.html, fetching live via cred1.json instead of a server-side
        service-account secret."""
        qs = parse_qs(urlparse(self.path).query)
        spreadsheet_id = qs.get("spreadsheetId", [""])[0]
        rng = qs.get("range", [""])[0]
        if not spreadsheet_id or not rng:
            self._json_response(400, json.dumps({"error": "spreadsheetId and range are required"}).encode())
            return
        try:
            from fetch import build_service
            service = build_service()
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=rng, valueRenderOption="FORMATTED_VALUE"
            ).execute()
            body = json.dumps({"values": result.get("values", [])}).encode()
            self._json_response(200, body)
        except Exception as e:
            self._json_response(500, json.dumps({"error": str(e)}).encode())

    def _handle_refresh(self):
        print("  --> Fetching latest data from Google Sheets...")
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "fetch.py")],
                capture_output=True,
                text=True,
                cwd=ROOT,
                timeout=60,
            )
            if result.returncode == 0:
                with open(os.path.join(ROOT, "data", "supply_index.json"), "rb") as f:
                    body = f.read()
                print("  --> OK: data refreshed")
                self._json_response(200, body)
            else:
                msg = (result.stderr or result.stdout or "fetch.py exited with error").strip()
                print(f"  --> FAIL: {msg}")
                self._json_response(500, json.dumps({"error": msg}).encode())
        except subprocess.TimeoutExpired:
            self._json_response(504, json.dumps({"error": "Fetch timed out after 60s"}).encode())
        except Exception as e:
            self._json_response(500, json.dumps({"error": str(e)}).encode())

    def _json_response(self, status, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        if "/api/" in str(args[0]):
            print(f"[{self.log_date_time_string()}] {args[0]}")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    os.chdir(ROOT)
    httpd = ThreadingHTTPServer(("", port), DashboardHandler)
    print(f"Dashboard server running at http://localhost:{port}")
    print("Press Ctrl+C to stop.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
