import json
import logging
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

SIGNAL_API_URL = os.environ.get(
    "SIGNAL_API_URL",
    "http://signal-api:8080/v2/send",
)
SIGNAL_NUMBER = os.environ["SIGNAL_NUMBER"]
SIGNAL_RECIPIENTS = [
    value.strip()
    for value in os.environ["SIGNAL_RECIPIENTS"].split(",")
    if value.strip()
]


def send_signal(event: dict) -> None:
    metadata = event.get("metadata") or {}

    image = event.get("image") or "Unknown image"
    status = str(event.get("status") or "update").upper()
    containers = metadata.get("ctn_names") or "Unknown container"
    hub_link = event.get("hub_link") or ""

    message_lines = [
        "🔔 CONTAINER UPDATE",
        "",
        f"Image: {image}",
        f"Status: {status}",
        f"Container: {containers}",
    ]

    if hub_link:
        message_lines.extend(["", hub_link])

    payload = {
        "message": "\n".join(message_lines),
        "number": SIGNAL_NUMBER,
        "recipients": SIGNAL_RECIPIENTS,
    }

    request = urllib.request.Request(
        SIGNAL_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError(f"Signal API returned HTTP {response.status}")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404)
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def do_POST(self) -> None:
        if self.path != "/diun":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            event = json.loads(self.rfile.read(content_length))
            send_signal(event)

            logging.info(
                "Signal notification sent for image %s",
                event.get("image", "unknown"),
            )

            self.send_response(204)
            self.end_headers()

        except (
            ValueError,
            KeyError,
            RuntimeError,
            urllib.error.URLError,
        ) as error:
            logging.exception("Notification failed: %s", error)
            self.send_error(500, str(error))

    def log_message(self, format_string: str, *args: object) -> None:
        return


if __name__ == "__main__":
    logging.info("DIUN Signal bridge listening on port 8080")
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
