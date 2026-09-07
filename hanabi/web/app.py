"""Tiny dependency-free HTTP server for the Hanabi convention lab."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .service import (
    analyze_position,
    card_kind_matrix,
    config_payload,
    continue_position,
    default_position,
    likely_position,
    ask_play_bot,
    play_game_move,
    rewind_play_game,
    restore_play_game,
    recording_play_game,
    validate_position,
    recommendation_codes,
    replay_history,
    simulate_game,
    start_play_game,
)


BUNDLED_STATIC_DIR = Path(__file__).with_name("static")
SITE_STATIC_DIR = Path(__file__).parents[2] / "site" / "public"
if all((SITE_STATIC_DIR / name).is_file() for name in ("app.js", "lab.html", "styles.css")):
    # In the project workspace, the deployable Site is the canonical Lab UI.
    STATIC_DIR = SITE_STATIC_DIR
    STATIC_INDEX = STATIC_DIR / "lab.html"
else:
    # Installed engine packages retain a self-contained fallback copy.
    STATIC_DIR = BUNDLED_STATIC_DIR
    STATIC_INDEX = STATIC_DIR / "index.html"
MAX_BODY_BYTES = 6 * 1024 * 1024


class HanabiWebHandler(BaseHTTPRequestHandler):
    server_version = "HanabiConventionLab/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/config":
            self._json_response(config_payload())
            return
        if path == "/api/default-position":
            self._json_response(default_position())
            return
        if path in ("/", "/index.html"):
            self._static_response(STATIC_INDEX)
            return
        candidate = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR.resolve() not in candidate.parents or not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._static_response(candidate)

    def do_POST(self) -> None:
        routes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "/api/default-position": lambda payload: default_position(str(payload.get("bot", "simple-3p"))),
            "/api/analyze": analyze_position,
            "/api/card-kinds": card_kind_matrix,
            "/api/continue-position": continue_position,
            "/api/likely-position": likely_position,
            "/api/play/move": play_game_move,
            "/api/play/ask": ask_play_bot,
            "/api/play/rewind": rewind_play_game,
            "/api/play/restore": restore_play_game,
            "/api/play/recording": recording_play_game,
            "/api/validate-position": validate_position,
            "/api/play/start": start_play_game,
            "/api/recommendations": recommendation_codes,
            "/api/simulate": simulate_game,
            "/api/replay": replay_history,
        }
        path = urlparse(self.path).path
        handler = routes.get(path)
        if handler is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_json_body()
            self._json_response(handler(payload))
        except (ValueError, AssertionError, KeyError, json.JSONDecodeError) as error:
            self._json_response({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as error:  # Keep the browser usable while preserving a concise failure.
            self._json_response({"error": f"{type(error).__name__}: {error}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[hanabi-web] {self.address_string()} {format % args}")

    def _read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid Content-Length") from error
        if not 0 < length <= MAX_BODY_BYTES:
            raise ValueError("request body is empty or too large")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _json_response(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static_response(self, path: Path) -> None:
        body = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), HanabiWebHandler)
    print(f"Hanabi Convention Lab running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Hanabi Convention Lab")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(args.host, args.port)
