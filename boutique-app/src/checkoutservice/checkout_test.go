package main

import (
	"context"
	"net"
	"testing"
	"time"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/checkoutservice/genproto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
	"google.golang.org/grpc/test/bufconn"
)

// External dependencies run on an in-memory gRPC transport; checkout itself is real.
func TestCurrencyConversionPreservesCancellation(t *testing.T) {
	conn, err := grpc.NewClient("passthrough:///currency-test",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithUnaryInterceptor(func(ctx context.Context, method string, req, reply interface{},
			cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {
			if ctx.Err() != context.Canceled {
				t.Error("currency conversion lost request cancellation")
			}
			return context.Canceled
		}))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	service := &checkoutService{currencySvcConn: conn}
	if _, err := service.convertCurrency(ctx, &pb.Money{CurrencyCode: "USD"}, "EUR"); err == nil {
		t.Fatal("canceled conversion must fail")
	}
}

type orderBackends struct {
	pb.UnimplementedCartServiceServer
	pb.UnimplementedProductCatalogServiceServer
	pb.UnimplementedCurrencyServiceServer
	pb.UnimplementedShippingServiceServer
	pb.UnimplementedPaymentServiceServer
	pb.UnimplementedEmailServiceServer
	items       []*pb.CartItem
	charged     *pb.ChargeRequest
	shipment    *pb.ShipOrderRequest
	email       *pb.SendOrderConfirmationRequest
	failPayment bool
}

func (b *orderBackends) GetCart(_ context.Context, req *pb.GetCartRequest) (*pb.Cart, error) {
	return &pb.Cart{UserId: req.UserId, Items: b.items}, nil
}

func (b *orderBackends) EmptyCart(context.Context, *pb.EmptyCartRequest) (*pb.Empty, error) {
	b.items = nil
	return &pb.Empty{}, nil
}

func (b *orderBackends) GetProduct(_ context.Context, req *pb.GetProductRequest) (*pb.Product, error) {
	return &pb.Product{Id: req.Id, PriceUsd: &pb.Money{CurrencyCode: "USD", Units: 10, Nanos: 250000000}}, nil
}

func (b *orderBackends) Convert(_ context.Context, req *pb.CurrencyConversionRequest) (*pb.Money, error) {
	return &pb.Money{CurrencyCode: req.ToCode, Units: req.From.Units, Nanos: req.From.Nanos}, nil
}

func (b *orderBackends) GetQuote(context.Context, *pb.GetQuoteRequest) (*pb.GetQuoteResponse, error) {
	return &pb.GetQuoteResponse{CostUsd: &pb.Money{CurrencyCode: "USD", Units: 5}}, nil
}

func (b *orderBackends) ShipOrder(_ context.Context, req *pb.ShipOrderRequest) (*pb.ShipOrderResponse, error) {
	b.shipment = req
	return &pb.ShipOrderResponse{TrackingId: "tracking-test"}, nil
}

func (b *orderBackends) Charge(_ context.Context, req *pb.ChargeRequest) (*pb.ChargeResponse, error) {
	b.charged = req
	if b.failPayment {
		return nil, status.Error(codes.InvalidArgument, "card rejected")
	}
	return &pb.ChargeResponse{TransactionId: "transaction-test"}, nil
}

func (b *orderBackends) SendOrderConfirmation(_ context.Context, req *pb.SendOrderConfirmationRequest) (*pb.Empty, error) {
	b.email = req
	return &pb.Empty{}, nil
}

func TestPlaceOrder(t *testing.T) {
	for _, declined := range []bool{false, true} {
		name := "success"
		if declined {
			name = "payment_declined"
		}
		t.Run(name, func(t *testing.T) {
			backends := &orderBackends{
				items:       []*pb.CartItem{{ProductId: "product-test", Quantity: 2}},
				failPayment: declined,
			}
			listener := bufconn.Listen(1024 * 1024)
			t.Cleanup(func() { listener.Close() })
			server := grpc.NewServer()
			t.Cleanup(server.Stop)
			pb.RegisterCartServiceServer(server, backends)
			pb.RegisterProductCatalogServiceServer(server, backends)
			pb.RegisterCurrencyServiceServer(server, backends)
			pb.RegisterShippingServiceServer(server, backends)
			pb.RegisterPaymentServiceServer(server, backends)
			pb.RegisterEmailServiceServer(server, backends)
			conn, err := grpc.NewClient("passthrough:///checkout-test",
				grpc.WithTransportCredentials(insecure.NewCredentials()),
				grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) { return listener.Dial() }))
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() { conn.Close() })
			pb.RegisterCheckoutServiceServer(server, &checkoutService{
				cartSvcConn: conn, productCatalogSvcConn: conn, currencySvcConn: conn,
				shippingSvcConn: conn, paymentSvcConn: conn, emailSvcConn: conn,
			})
			go server.Serve(listener)
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			result, err := pb.NewCheckoutServiceClient(conn).PlaceOrder(ctx, &pb.PlaceOrderRequest{
				UserId: "user-test", UserCurrency: "USD", Email: "test@example.com",
				Address: &pb.Address{StreetAddress: "123 Test Street"}, CreditCard: &pb.CreditCardInfo{},
			})
			if declined {
				if status.Code(err) != codes.Internal {
					t.Fatalf("declined payment: got %v, want Internal", err)
				}
				if len(backends.items) != 1 || backends.shipment != nil || backends.email != nil {
					t.Fatal("declined payment must preserve the cart and stop shipping and confirmation")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			order := result.GetOrder()
			if order.OrderId == "" || order.ShippingTrackingId != "tracking-test" || len(order.Items) != 1 {
				t.Fatalf("incomplete order: %v", order)
			}
			// Two items at $10.25 plus $5 shipping = $25.50.
			if backends.charged == nil || backends.charged.Amount.Units != 25 || backends.charged.Amount.Nanos != 500000000 {
				t.Fatalf("incorrect charge: %v", backends.charged)
			}
			if len(backends.items) != 0 || backends.shipment == nil || backends.email == nil || backends.email.Order.OrderId != order.OrderId {
				t.Fatal("successful checkout must ship, empty the cart and confirm the same order")
			}
		})
	}
}
