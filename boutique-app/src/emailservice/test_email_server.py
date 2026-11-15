from concurrent import futures
import unittest

import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc

import demo_pb2
import demo_pb2_grpc
from email_server import DummyEmailService


class EmailServiceTests(unittest.TestCase):
    def setUp(self):
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        service = DummyEmailService()
        demo_pb2_grpc.add_EmailServiceServicer_to_server(service, server)
        health_pb2_grpc.add_HealthServicer_to_server(service, server)
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        self.addCleanup(lambda: server.stop(0).wait())
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        self.addCleanup(channel.close)
        self.health = health_pb2_grpc.HealthStub(channel)
        self.email = demo_pb2_grpc.EmailServiceStub(channel)

    def test_health_check_reports_serving(self):
        response = self.health.Check(health_pb2.HealthCheckRequest(), timeout=5)
        self.assertEqual(response.status, health_pb2.HealthCheckResponse.SERVING)

    def test_health_watch_reports_unimplemented(self):
        with self.assertRaises(grpc.RpcError) as error:
            next(self.health.Watch(health_pb2.HealthCheckRequest(), timeout=5))
        self.assertEqual(error.exception.code(), grpc.StatusCode.UNIMPLEMENTED)

    def test_dummy_order_confirmation_succeeds_without_mail_provider(self):
        response = self.email.SendOrderConfirmation(
            demo_pb2.SendOrderConfirmationRequest(
                email="shopper@example.invalid",
                order=demo_pb2.OrderResult(order_id="test-order"),
            ),
            timeout=5,
        )
        self.assertEqual(response, demo_pb2.Empty())


if __name__ == "__main__":
    unittest.main()
