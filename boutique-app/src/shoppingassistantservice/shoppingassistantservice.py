#!/usr/bin/python
#
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from functools import lru_cache
from typing import Any, Callable
from urllib.parse import unquote

from flask import Flask, jsonify, request

REQUIRED_ENV_VARS = (
    "PROJECT_ID",
    "REGION",
    "ALLOYDB_DATABASE_NAME",
    "ALLOYDB_TABLE_NAME",
    "ALLOYDB_CLUSTER_NAME",
    "ALLOYDB_INSTANCE_NAME",
    "ALLOYDB_SECRET_NAME",
)


@lru_cache(maxsize=1)
def _default_backends() -> tuple[Any, Callable[[], Any], Callable[[], Any]]:
    missing = [key for key in REQUIRED_ENV_VARS if not os.environ.get(key, "").strip()]
    if missing:
        raise RuntimeError(
            "Missing required GCP configuration for shoppingassistantservice: "
            + ", ".join(missing)
        )

    from google.cloud import secretmanager_v1
    from langchain_google_alloydb_pg import AlloyDBEngine, AlloyDBVectorStore
    from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

    project_id = os.environ["PROJECT_ID"]
    secret_client = secretmanager_v1.SecretManagerServiceClient()
    secret_name = secret_client.secret_version_path(
        project=project_id,
        secret=os.environ["ALLOYDB_SECRET_NAME"],
        secret_version="latest",
    )
    secret_response = secret_client.access_secret_version(
        request=secretmanager_v1.AccessSecretVersionRequest(name=secret_name)
    )
    pg_password = secret_response.payload.data.decode("UTF-8").strip()

    engine = AlloyDBEngine.from_instance(
        project_id=project_id,
        region=os.environ["REGION"],
        cluster=os.environ["ALLOYDB_CLUSTER_NAME"],
        instance=os.environ["ALLOYDB_INSTANCE_NAME"],
        database=os.environ["ALLOYDB_DATABASE_NAME"],
        user="postgres",
        password=pg_password,
    )
    store = AlloyDBVectorStore.create_sync(
        engine=engine,
        table_name=os.environ["ALLOYDB_TABLE_NAME"],
        embedding_service=GoogleGenerativeAIEmbeddings(model="models/embedding-001"),
        id_column="id",
        content_column="description",
        embedding_column="product_embedding",
        metadata_columns=["id", "name", "categories"],
    )
    model_factory = lambda: ChatGoogleGenerativeAI(model="gemini-1.5-flash")
    return store, model_factory, model_factory


def _build_vision_message(image_url: str) -> Any:
    payload = [
        {
            "type": "text",
            "text": (
                "You are a professional interior designer, give me a detailed "
                "description of the style of the room in this image"
            ),
        },
        {"type": "image_url", "image_url": image_url},
    ]
    try:
        from langchain_core.messages import HumanMessage

        return HumanMessage(content=payload)
    except ModuleNotFoundError:
        return {"role": "user", "content": payload}


def create_app(
    vectorstore: Any = None,
    vision_model_factory: Callable[[], Any] | None = None,
    design_model_factory: Callable[[], Any] | None = None,
) -> Flask:
    app = Flask(__name__)

    @app.route("/_healthz", methods=["GET"])
    def healthz():
        return "ok", 200

    @app.route("/", methods=["POST"])
    def talkToGemini():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not payload.get("message") or not payload.get("image"):
            return jsonify({"error": "JSON body must include non-empty 'message' and 'image'"}), 400

        store, vision_factory, design_factory = (
            (vectorstore, vision_model_factory, design_model_factory)
            if vectorstore is not None
            and vision_model_factory is not None
            and design_model_factory is not None
            else _default_backends()
        )

        prompt = unquote(str(payload["message"]))
        llm_vision = vision_factory()
        vision_response = llm_vision.invoke([_build_vision_message(str(payload["image"]))])
        description_response = vision_response.content

        vector_search_prompt = (
            f" This is the user's request: {prompt} Find the most relevant items for that prompt, "
            f"while matching style of the room described here: {description_response} "
        )
        docs = store.similarity_search(vector_search_prompt)
        relevant_docs = "".join(f"{doc.to_json()}, " for doc in docs)

        llm = design_factory()
        design_prompt = (
            " You are an interior designer that works for Online Boutique. You are tasked with "
            "providing recommendations to a customer on what they should add to a given room from "
            f"our catalog. This is the description of the room: \n{description_response} Here are "
            f"a list of products that are relevant to it: {relevant_docs} Specifically, this is "
            f"what the customer has asked for, see if you can accommodate it: {prompt} Start by "
            "repeating a brief description of the room's design to the customer, then provide your "
            "recommendations. Do your best to pick the most relevant item out of the list of "
            "products provided, but if none of them seem relevant, then say that instead of "
            "inventing a new product. At the end of the response, add a list of the IDs of the "
            "relevant products in the following format for the top 3 results: "
            "[<first product ID>], [<second product ID>], [<third product ID>] "
        )
        design_response = llm.invoke(design_prompt)
        return jsonify({"content": design_response.content})

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    create_app().run(host="0.0.0.0", port=port)
