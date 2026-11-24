import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock


def _load_locustfile():
    try:
        import faker  # noqa: F401
        import locust  # noqa: F401
    except ModuleNotFoundError:
        stub_locust = types.ModuleType("locust")
        stub_locust.FastHttpUser = type("FastHttpUser", (), {})
        stub_locust.TaskSet = type("TaskSet", (), {})
        stub_locust.between = lambda low, high: (low, high)
        sys.modules.setdefault("locust", stub_locust)

        stub_faker = types.ModuleType("faker")
        stub_faker.Faker = lambda: types.SimpleNamespace(
            email=lambda: "buyer@example.com",
            street_address=lambda: "123 Market St",
            zipcode=lambda: "94105",
            city=lambda: "San Francisco",
            state_abbr=lambda: "CA",
            country=lambda: "United States",
            credit_card_number=lambda card_type="visa": "4242424242424242",
        )
        sys.modules.setdefault("faker", stub_faker)
    return importlib.import_module("locustfile")


class LoadGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_locustfile()

    def test_navigation_and_currency_tasks(self):
        user = MagicMock(client=MagicMock())
        self.mod.index(user)
        self.mod.viewCart(user)
        self.mod.empty_cart(user)
        self.mod.logout(user)
        self.mod.setCurrency(user)
        self.mod.browseProduct(user)

        gets = [c.args[0] for c in user.client.get.call_args_list]
        self.assertEqual(gets[:3], ["/", "/cart", "/logout"])
        self.assertIn(gets[3].removeprefix("/product/"), self.mod.products)
        self.assertEqual(user.client.post.call_args_list[0].args, ("/cart/empty",))
        path, data = user.client.post.call_args_list[1].args
        self.assertEqual(path, "/setCurrency")
        self.assertIn(data["currency_code"], {"EUR", "USD", "JPY", "CAD", "GBP", "TRY"})

    def test_checkout_flow_and_taskset_registration(self):
        user = MagicMock(client=MagicMock())
        self.mod.checkout(user)
        cart_path, cart_data = user.client.post.call_args_list[0].args
        order_path, order = user.client.post.call_args_list[1].args
        self.assertEqual((cart_path, order_path), ("/cart", "/cart/checkout"))
        self.assertIn(cart_data["product_id"], self.mod.products)
        self.assertTrue(1 <= cart_data["quantity"] <= 10)
        self.assertTrue(str(order["credit_card_number"]).startswith("4"))
        self.assertEqual(len(str(order["credit_card_cvv"])), 3)
        self.assertIn(self.mod.UserBehavior, self.mod.WebsiteUser.tasks)
