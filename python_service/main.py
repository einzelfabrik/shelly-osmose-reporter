from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

from python_service.config import load_config
from python_service.service import OsmoseService


def run_scheduler(service: OsmoseService, cfg: dict[str, Any]) -> None:
    tick_seconds = int(cfg["runtime"].get("tick_seconds", 3600))
    send_time = str(cfg["runtime"].get("daily_send_time", "06:00"))
    while True:
        service.tick()
        now = datetime.now()
        if now.strftime("%H:%M") == send_time:
            if service.state.get("runtime", {}).get("last_sent_day") != now.strftime("%Y-%m-%d"):
                service.send_daily_report()
                time.sleep(65)
        time.sleep(tick_seconds)


def make_handler(service: OsmoseService):
    class Handler(BaseHTTPRequestHandler):
        def _write(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._write(200, {"ok": True, "time": datetime.now().isoformat()})
                return
            if self.path == "/report/test":
                service.tick()
                service.send_test_report()
                self._write(200, {"ok": True, "action": "test_report_sent"})
                return
            if self.path == "/report/daily":
                service.tick()
                sent = service.send_daily_report()
                self._write(200, {"ok": True, "sent": sent})
                return
            self._write(404, {"ok": False, "error": "not_found"})

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Osmose multi-target Python service")
    parser.add_argument("--config", default="examples/config.example.toml")
    parser.add_argument(
        "command",
        choices=["tick", "report-daily", "report-test", "run-scheduler", "serve"],
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    service = OsmoseService(cfg)

    if args.command == "tick":
        service.tick()
        return
    if args.command == "report-daily":
        service.tick()
        print("sent" if service.send_daily_report() else "no-yesterday-data")
        return
    if args.command == "report-test":
        service.tick()
        service.send_test_report()
        print("test-sent")
        return
    if args.command == "run-scheduler":
        run_scheduler(service, cfg)
        return

    if args.command == "serve":
        host = str(cfg["runtime"].get("http_host", "127.0.0.1"))
        port = int(cfg["runtime"].get("http_port", 8181))
        server = HTTPServer((host, port), make_handler(service))
        scheduler_thread = Thread(target=run_scheduler, args=(service, cfg), daemon=True)
        scheduler_thread.start()
        print(f"Server listening on http://{host}:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
