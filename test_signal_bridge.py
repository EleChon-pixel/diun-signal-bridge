"""Regression tests: authentication, body bounds, and health endpoint."""
import http.client
import os
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault("BRIDGE_WEBHOOK_TOKEN", "test-only-" + "x" * 48)
os.environ.setdefault("SIGNAL_NUMBER", "+10000000000")
os.environ.setdefault("SIGNAL_RECIPIENTS", "+10000000001")
from signal_bridge import BoundedServer, Handler  # noqa: E402


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = BoundedServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            code = response.status
            response.read()
            return code
        finally:
            conn.close()

    def test_health(self):
        self.assertEqual(self.request("GET", "/health"), 200)

    def test_rejects_missing_and_bad_token(self):
        with patch("signal_bridge.send_signal") as send:
            self.assertEqual(self.request("POST", "/diun", "{}", {"Content-Type": "application/json"}), 401)
            self.assertEqual(self.request("POST", "/diun", "{}", {
                "Content-Type": "application/json", "Authorization": "Bearer invalid"
            }), 401)
            send.assert_not_called()

    def test_authenticated_json(self):
        with patch("signal_bridge.send_signal") as send:
            code = self.request("POST", "/diun", '{"image":"test:v1","status":"update"}', {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + os.environ["BRIDGE_WEBHOOK_TOKEN"],
            })
            self.assertEqual(code, 204)
            send.assert_called_once()

    def test_rejects_oversize_and_non_json(self):
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["BRIDGE_WEBHOOK_TOKEN"]}
        with patch("signal_bridge.send_signal") as send:
            self.assertEqual(self.request("POST", "/diun", b"x" * 65537, headers), 413)
            self.assertEqual(self.request("POST", "/diun", "not-json", headers), 400)
            self.assertEqual(self.request("POST", "/diun", "{}", {**headers, "Content-Type": "text/plain"}), 415)
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
