import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import shoppingassistantservice


class ShoppingAssistantTests(unittest.TestCase):
    def setUp(self):
        shoppingassistantservice._default_backends.cache_clear()

    def test_healthz_succeeds_without_gcp_credentials(self):
        client = shoppingassistantservice.create_app().test_client()
        res = client.get("/_healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_data(as_text=True), "ok")

    def test_post_validates_required_json_fields(self):
        client = shoppingassistantservice.create_app().test_client()
        for bad_body in ({}, {"message": "chair"}, {"image": "https://example.com/room.jpg"}):
            with self.subTest(body=bad_body):
                res = client.post("/", json=bad_body)
                self.assertEqual(res.status_code, 400)

    def test_rag_pipeline_decodes_prompt_and_returns_recommendations(self):
        vision_llm = MagicMock()
        vision_llm.invoke.return_value = SimpleNamespace(content="Minimalist Scandinavian living room")
        design_llm = MagicMock()
        design_llm.invoke.return_value = SimpleNamespace(
            content="Scandinavian style room. Try these items: [0PUK6V6EV0], [1YMWWN1N4O], [2ZYFJ3GM2N]"
        )
        doc = MagicMock()
        doc.to_json.return_value = {"id": "0PUK6V6EV0", "name": "Candle Holder"}
        store = MagicMock()
        store.similarity_search.return_value = [doc]

        app = shoppingassistantservice.create_app(
            vectorstore=store,
            vision_model_factory=lambda: vision_llm,
            design_model_factory=lambda: design_llm,
        )
        res = app.test_client().post(
            "/",
            json={"message": "warm%20lighting", "image": "https://example.com/room.png"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("[0PUK6V6EV0]", res.get_json()["content"])
        search_query = store.similarity_search.call_args.args[0]
        self.assertIn("warm lighting", search_query)
        self.assertIn("Minimalist Scandinavian living room", search_query)

    def test_default_backends_reports_missing_gcp_env_vars_cleanly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "PROJECT_ID"):
                shoppingassistantservice._default_backends()


if __name__ == "__main__":
    unittest.main()
