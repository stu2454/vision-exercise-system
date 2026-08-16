"""Serve the browser sandbox and score its pose frames live.

    python tools/exercise_server.py
    open http://localhost:8000/web/

The browser captures, runs pose estimation and draws; this scores. Canonical
pose frames come in over HTTP, the existing Python pipeline processes them, and
the repetition count goes back. The exercise engine is therefore implemented
once, in Python, where the regression dataset can validate it — which is what
Document 03 §7 and ADR-010 ask for while the movement model is still changing.

Frames are posted in small batches rather than streamed over a WebSocket. That
keeps this to the standard library, and a repetition counter tolerates the
resulting delay comfortably: a repetition takes around two and a half seconds
against a batch interval of a tenth of one. It would *not* be adequate for the
reaction-timed stepping games, which is a reason that work needs the algorithm
settled and ported rather than bridged.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import threading
import uuid
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config, load_sts_config  # noqa: E402
from src.exercises.sit_to_stand import SitToStandEngine  # noqa: E402
from src.live_session import LiveSession  # noqa: E402
from src.pose.models import PoseFrame  # noqa: E402

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent

# Requests larger than this are refused rather than read into memory.
MAXIMUM_BODY_BYTES = 4 * 1024 * 1024


class SessionStore:
    """Live sessions, keyed by identifier.

    Guarded by a lock because the server is threaded: a browser can post a new
    batch before the previous response has been written.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, LiveSession] = {}
        self._lock = threading.Lock()

    def create(self, target: Optional[int] = None) -> str:
        config = load_config()
        sts_config = load_sts_config()
        if target is not None:
            sts_config = dataclasses.replace(sts_config, target_repetitions=target)
        # The caller owns the engine, so build it here and hand it over
        # already initialised.
        engine = SitToStandEngine(sts_config)
        engine.initialise()
        session_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._sessions[session_id] = LiveSession(config, engine=engine)
        return session_id

    def get(self, session_id: str) -> Optional[LiveSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def discard(self, session_id: str) -> Optional[LiveSession]:
        with self._lock:
            return self._sessions.pop(session_id, None)


STORE = SessionStore()


def score_batch(session: LiveSession, frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Run a batch of canonical pose frames through the pipeline."""
    events: list[dict[str, Any]] = []
    quality = None
    for raw in frames:
        pose = PoseFrame.from_dict(raw)
        update = session.update(pose)
        quality = update.quality
        events.extend(event.to_dict() for event in update.events)
    payload = session.status()
    payload["events"] = events
    payload["quality"] = quality.status.value if quality else None
    return payload


class Handler(SimpleHTTPRequestHandler):
    """Static files from the repository root, plus the scoring endpoints.

    Serving from the root rather than `web/` is deliberate: the page loads the
    pose model from `models/`, so both must be reachable, and both runtimes
    then load the identical model file.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPOSITORY_ROOT), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Quiet by default: a frame batch every 100 ms would bury anything
        # worth reading.
        if self.path.startswith("/api/"):
            return
        super().log_message(format, *args)

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Optional[dict[str, Any]]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAXIMUM_BODY_BYTES:
            self._send_json(
                {"error": "body missing or too large"}, HTTPStatus.BAD_REQUEST
            )
            return None
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send_json({"error": "body is not valid JSON"}, HTTPStatus.BAD_REQUEST)
            return None

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            self._handle_post()
        except Exception as exc:  # noqa: BLE001 - the browser needs an answer
            # Without this the connection is dropped and the page reports
            # "scorer unreachable", which points at the network rather than
            # at the actual fault.
            import traceback

            traceback.print_exc()
            self._send_json(
                {"error": f"{type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _handle_post(self) -> None:
        if not self.path.startswith("/api/"):
            self._send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
            return
        data = self._read_json()
        if data is None:
            return

        if self.path == "/api/session":
            session_id = STORE.create(target=data.get("target"))
            self._send_json({"session": session_id})
            return

        session_id = str(data.get("session", ""))
        session = STORE.get(session_id)
        if session is None:
            # Say which thing is missing, so the browser can start a new
            # session rather than retrying a dead one.
            self._send_json(
                {"error": "no such session", "session": session_id},
                HTTPStatus.NOT_FOUND,
            )
            return

        if self.path == "/api/frames":
            frames = data.get("frames") or []
            if not isinstance(frames, list):
                self._send_json({"error": "frames must be a list"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                self._send_json(score_batch(session, frames))
            except (KeyError, TypeError, ValueError) as exc:
                self._send_json(
                    {"error": f"malformed pose frame: {exc}"}, HTTPStatus.BAD_REQUEST
                )
            return

        if self.path == "/api/stop":
            session.stop()
            result = session.result().to_dict()
            STORE.discard(session_id)
            self._send_json({"result": result})
            return

        self._send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Vision Exercise System — browser sandbox with live scoring")
    print(f"  serving  {REPOSITORY_ROOT}")
    print(f"  open     http://{args.host}:{args.port}/web/")
    print("  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
