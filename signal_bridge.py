"""Authenticated, resource-bounded DIUN webhook -> Signal relay.

Only the internal Docker network should be able to reach this service. The
shared bearer token provides a second boundary if another container can
reach the network. Never print the token or incoming webhook payloads.
"""
import hmac
import json
import logging
import os
import re
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SIGNAL_API_URL = os.environ.get("SIGNAL_API_URL", "http://signal-api:8080/v2/send")
SIGNAL_NUMBER = os.environ.get("SIGNAL_NUMBER", "")
SIGNAL_RECIPIENTS = [
    value.strip() for value in os.environ.get("SIGNAL_RECIPIENTS", "").split(",")
    if value.strip()
]
BRIDGE_WEBHOOK_TOKEN = os.environ.get("BRIDGE_WEBHOOK_TOKEN", "")
MAX_REQUEST_BYTES = 65536
MAX_CONCURRENT_REQUESTS = 8
REQUEST_TIMEOUT_SECONDS = 5


def require_configuration() -> None:
    if len(BRIDGE_WEBHOOK_TOKEN) < 32 or not SIGNAL_NUMBER or not SIGNAL_RECIPIENTS:
        raise RuntimeError(
            "Set BRIDGE_WEBHOOK_TOKEN (at least 32 characters), SIGNAL_NUMBER and SIGNAL_RECIPIENTS."
        )


def safe_field(value: object, limit: int = 160) -> str:
    """Keep untrusted metadata out of multiline/oversized Signal messages."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()[:limit]


def send_signal(event: dict) -> None:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    image = safe_field(event.get("image"), 200) or "Unknown image"
    status = (safe_field(event.get("status"), 40) or "update").upper()
    containers = safe_field(metadata.get("ctn_names"), 200) or "Unknown container"
    hub_link = safe_field(event.get("hub_link"), 300)
    if not hub_link.startswith(("https://", "http://")):
        hub_link = ""

    message_lines = [
        "🔔 CONTAINER UPDATE", "",
        f"Image: {image}", f"Status: {status}", f"Container: {containers}",
    ]
    if hub_link:
        message_lines.extend(["", hub_link])

    payload = {
        "message": "\n".join(message_lines),
        "number": SIGNAL_NUMBER,
        "recipients": SIGNAL_RECIPIENTS,
    }
    req = urllib.request.Request(
        SIGNAL_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError("Signal API rejected the request")


class Handler(BaseHTTPRequestHandler):
    server_version = "DIUNBridge"
    sys_version = ""

    def respond(self, code: int) -> None:
        self.send_response(code)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/health":
            self.respond(200)
        else:
            self.respond(404)

    def do_POST(self) -> None:
        if self.path != "/diun":
            return self.respond(404)
        expected = BRIDGE_WEBHOOK_TOKEN
        received = self.headers.get("Authorization", "")
        if len(expected) < 32 or not hmac.compare_digest(received, "Bearer " + expected):
            return self.respond(401)

        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            return self.respond(415)
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            return self.respond(400)
        try:
            size = int(self.headers["Content-Length"])
        except (TypeError, ValueError):
            return self.respond(400)
        if size <= 0:
            return self.respond(400)
        if size > MAX_REQUEST_BYTES:
            return self.respond(413)
        try:
            payload = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError, socket.timeout, TimeoutError):
            return self.respond(400)
        if not isinstance(payload, dict):
            return self.respond(400)
        try:
            send_signal(payload)
        except (OSError, ValueError, RuntimeError, urllib.error.URLError):
            logging.exception("Signal delivery failed")
            return self.respond(502)
        logging.info("DIUN notification delivered")
        return self.respond(204)

    def log_message(self, format_string: str, *args: object) -> None:
        # Never log untrusted URLs, the Authorization header, or webhook bodies.
        return


class BoundedServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = MAX_CONCURRENT_REQUESTS

    def __init__(self, address, handler):
        super().__init__(address, handler)
        self.slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(REQUEST_TIMEOUT_SECONDS)
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


if __name__ == "__main__":
    require_configuration()
    logging.info("DIUN Signal bridge listening on internal port 8080")
    BoundedServer(("0.0.0.0", 8080), Handler).serve_forever()
