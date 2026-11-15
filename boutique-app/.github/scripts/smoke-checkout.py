"""Place one synthetic order against a running Online Boutique lab storefront."""

import argparse
from datetime import date
from html.parser import HTMLParser
from http.cookiejar import CookieJar
import re
import sys
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, build_opener


class OrderText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def smoke_checkout(base_url: str) -> None:
    client = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(path: str, fields: dict | None = None) -> str:
        data = urlencode(fields).encode() if fields is not None else None
        with client.open(base_url.rstrip("/") + path, data=data, timeout=15) as response:
            return response.read().decode("utf-8")

    product = "0PUK6V6EV0"
    request("/_healthz")
    request("/")
    request("/setCurrency", {"currency_code": "USD"})
    request("/product/" + product)
    request("/cart", {"product_id": product, "quantity": 1})
    cart = request("/cart")
    if product not in cart or not re.search(r"Quantity:\s*1\b", cart):
        raise ValueError("The selected product did not appear in the session cart")
    order = request("/cart/checkout", {
        "email": "smoke@example.com", "street_address": "123 Test Street", "zip_code": "94043",
        "city": "Mountain View", "state": "CA", "country": "United States",
        "credit_card_number": "4111111111111111", "credit_card_expiration_month": 12,
        "credit_card_expiration_year": date.today().year + 1, "credit_card_cvv": "123",
    })
    page = OrderText()
    page.feed(order)
    text = " ".join(" ".join(page.parts).split())
    identifiers = re.search(r"Confirmation #\s*(.*?)\s*Tracking #\s*(.*?)\s*Total Paid\b", text)
    if (
        "Your order is complete!" not in text
        or identifiers is None
        or not all(value.strip() for value in identifiers.groups())
    ):
        raise ValueError("Checkout did not return an order confirmation and tracking information")
    if "Your shopping cart is empty!" not in request("/cart"):
        raise ValueError("Checkout did not empty the session cart")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    args = parser.parse_args()
    try:
        smoke_checkout(args.base_url)
    except (OSError, URLError, ValueError) as exc:
        print(f"Checkout smoke test failed: {exc}", file=sys.stderr)
        return 1
    print("Checkout smoke test passed: product, cart, order confirmation and empty cart")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
