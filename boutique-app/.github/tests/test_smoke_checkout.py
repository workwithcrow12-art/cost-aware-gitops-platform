import http.server
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from urllib.parse import parse_qs


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke-checkout.py"


class Storefront(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = "ok"
        if self.path == "/cart":
            body = "SKU #0PUK6V6EV0 Quantity: 1" if self.server.has_item else "Your shopping cart is empty!"
        self.send_response(200)
        self.send_header("Set-Cookie", "session=test-session; Path=/")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):
        form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
        if self.headers.get("Cookie") != "session=test-session":
            self.send_error(401)
            return
        body = "ok"
        if self.path == "/cart":
            self.server.has_item = form.get("product_id") == ["0PUK6V6EV0"] and form.get("quantity") == ["1"]
        if self.path == "/cart/checkout":
            if self.server.checkout_status != 200:
                self.send_error(self.server.checkout_status)
                return
            if not self.server.has_item or form.get("credit_card_number") != ["4111111111111111"]:
                self.send_error(400)
                return
            self.server.has_item = False
            body = (
                "<h3>Your order is complete!</h3><div>Confirmation #</div>"
                f"<div>{self.server.order_id}</div><div>Tracking #</div>"
                f"<div>{self.server.tracking_id}</div><div>Total Paid</div><div>$25.50</div>"
            ) if self.server.confirm else "error page"
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body.encode())


class SmokeCheckoutTests(unittest.TestCase):
    def setUp(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Storefront)
        server.has_item = False
        server.checkout_status = 200
        server.confirm = True
        server.order_id = "order-test"
        server.tracking_id = "tracking-test"
        self.server = server
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def run_smoke(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--base-url", f"http://127.0.0.1:{self.server.server_port}"],
            capture_output=True, text=True, timeout=15,
        )

    def test_completes_checkout_with_one_session_and_empties_cart(self):
        result = self.run_smoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Checkout smoke test passed", result.stdout)
        self.assertFalse(self.server.has_item)

    def test_checkout_http_failure_fails_the_command(self):
        self.server.checkout_status = 500
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("HTTP Error 500", result.stderr)

    def test_http_200_without_an_order_confirmation_fails_the_command(self):
        self.server.confirm = False
        result = self.run_smoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not return an order confirmation", result.stderr)

    def test_empty_order_or_tracking_id_fails_the_command(self):
        for field in ("order_id", "tracking_id"):
            with self.subTest(field=field):
                self.server.order_id = "order-test"
                self.server.tracking_id = "tracking-test"
                setattr(self.server, field, " \n ")
                result = self.run_smoke()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("did not return an order confirmation", result.stderr)
