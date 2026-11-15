from concurrent import futures
import unittest
from unittest.mock import patch

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

import demo_pb2
import demo_pb2_grpc
import recommendation_server


class ProductCatalog(demo_pb2_grpc.ProductCatalogServiceServicer):
    def __init__(self):
        self.products = []

    def ListProducts(self, request, context):
        return demo_pb2.ListProductsResponse(products=self.products)


class RecommendationServiceTests(unittest.TestCase):
    def setUp(self):
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        service = recommendation_server.RecommendationService()
        self.catalog = ProductCatalog()
        demo_pb2_grpc.add_ProductCatalogServiceServicer_to_server(self.catalog, server)
        demo_pb2_grpc.add_RecommendationServiceServicer_to_server(service, server)
        health_pb2_grpc.add_HealthServicer_to_server(service, server)
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        self.addCleanup(lambda: server.stop(0).wait())
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        self.addCleanup(channel.close)
        catalog = patch.object(
            recommendation_server,
            "product_catalog_stub",
            demo_pb2_grpc.ProductCatalogServiceStub(channel),
            create=True,
        )
        catalog.start()
        self.addCleanup(catalog.stop)
        self.health = health_pb2_grpc.HealthStub(channel)
        self.recommendations = demo_pb2_grpc.RecommendationServiceStub(channel)

    def test_health_check_reports_serving(self):
        response = self.health.Check(health_pb2.HealthCheckRequest(), timeout=5)
        self.assertEqual(response.status, health_pb2.HealthCheckResponse.SERVING)

    def test_health_watch_reports_unimplemented(self):
        with self.assertRaises(grpc.RpcError) as error:
            next(self.health.Watch(health_pb2.HealthCheckRequest(), timeout=5))
        self.assertEqual(error.exception.code(), grpc.StatusCode.UNIMPLEMENTED)

    def test_recommendations_exclude_requested_products_and_duplicates(self):
        self.catalog.products = [
            demo_pb2.Product(id=product_id)
            for product_id in ["in-cart", "available", "available", "other"]
        ]
        response = self.recommendations.ListRecommendations(
            demo_pb2.ListRecommendationsRequest(product_ids=["in-cart"]), timeout=5
        )
        self.assertCountEqual(response.product_ids, ["available", "other"])

    def test_recommendations_are_limited_to_five_catalog_products(self):
        product_ids = [f"product-{number}" for number in range(10)]
        self.catalog.products = [demo_pb2.Product(id=product_id) for product_id in product_ids]
        response = self.recommendations.ListRecommendations(
            demo_pb2.ListRecommendationsRequest(), timeout=5
        )
        self.assertEqual(len(response.product_ids), 5)
        self.assertEqual(len(set(response.product_ids)), 5)
        self.assertTrue(set(response.product_ids).issubset(product_ids))

    def test_empty_catalog_has_no_recommendations(self):
        response = self.recommendations.ListRecommendations(
            demo_pb2.ListRecommendationsRequest(), timeout=5
        )
        self.assertEqual(list(response.product_ids), [])

    def test_no_recommendations_when_every_product_is_already_requested(self):
        self.catalog.products = [demo_pb2.Product(id="in-cart")]
        response = self.recommendations.ListRecommendations(
            demo_pb2.ListRecommendationsRequest(product_ids=["in-cart"]), timeout=5
        )
        self.assertEqual(list(response.product_ids), [])


if __name__ == "__main__":
    unittest.main()
