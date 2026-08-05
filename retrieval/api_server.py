"""HTTP API for deterministic collateral suggestion.

Run:
    python3 -m retrieval.api_server
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

from dotenv import load_dotenv

from retrieval.suggestion_agent import suggest_asset

load_dotenv(override=True)


class SuggestionHandler(BaseHTTPRequestHandler):
    """Minimal API handler for collateral suggestion requests."""

    server_version = "CollateralSuggestionAPI/1.0"

    def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/suggest":
            self._send_json(404, {"error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            req = json.loads(raw)
        except Exception:
            self._send_json(400, {"error": "invalid_json"})
            return

        company_name = str(req.get("company_name", "")).strip()
        current_asset = str(req.get("current_asset", "")).strip()

        try:
            loan_value = float(req.get("loan_value"))
        except Exception:
            self._send_json(400, {"error": "loan_value_must_be_number"})
            return

        try:
            current_asset_value = float(req.get("current_asset_value", 0.0))
        except Exception:
            current_asset_value = 0.0

        if not company_name or not current_asset:
            self._send_json(400, {"error": "company_name_and_current_asset_required"})
            return

        try:
            result = suggest_asset(
                company_name=company_name,
                loan_value=loan_value,
                current_asset=current_asset,
                current_asset_value=current_asset_value,
            )
            self._send_json(200, result)
        except Exception as exc:
            self._send_json(500, {"error": "suggestion_failed", "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        # Keep endpoint output focused on business logs.
        return


def main() -> None:
    host = "127.0.0.1"
    port = 8000
    server = ThreadingHTTPServer((host, port), SuggestionHandler)
    print(f"Suggestion API listening on http://{host}:{port}")
    print("Endpoints: GET /health, POST /suggest")
    server.serve_forever()


if __name__ == "__main__":
    main()
