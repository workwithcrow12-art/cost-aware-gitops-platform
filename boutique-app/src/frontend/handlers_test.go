package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/sirupsen/logrus"
)

type trackingBody struct {
	io.Reader
	closed atomic.Bool
}

func (b *trackingBody) Close() error {
	b.closed.Store(true)
	return nil
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) {
	return f(r)
}

func TestChatBotHandlerClosesResponseBodyOnSuccessAndFailure(t *testing.T) {
	originalClient := assistantHTTPClient
	t.Cleanup(func() { assistantHTTPClient = originalClient })

	cases := []struct {
		name           string
		upstreamStatus int
		upstreamBody   string
		expectedStatus int
		expectedReply  string
	}{
		{
			name:           "valid response",
			upstreamStatus: http.StatusOK,
			upstreamBody:   `{"content":"Try the minimalist desk lamp"}`,
			expectedStatus: http.StatusOK,
			expectedReply:  "Try the minimalist desk lamp",
		},
		{
			name:           "upstream failure status",
			upstreamStatus: http.StatusServiceUnavailable,
			upstreamBody:   `{"error":"unavailable"}`,
			expectedStatus: http.StatusBadGateway,
		},
		{
			name:           "malformed upstream json",
			upstreamStatus: http.StatusOK,
			upstreamBody:   `not-json`,
			expectedStatus: http.StatusInternalServerError,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			tb := &trackingBody{Reader: strings.NewReader(tc.upstreamBody)}
			assistantHTTPClient = &http.Client{
				Transport: roundTripFunc(func(_ *http.Request) (*http.Response, error) {
					return &http.Response{
						StatusCode: tc.upstreamStatus,
						Header:     make(http.Header),
						Body:       tb,
					}, nil
				}),
			}

			fe := &frontendServer{shoppingAssistantSvcAddr: "assistant.test:8080"}
			req := httptest.NewRequest(http.MethodPost, "http://example.test/bot", strings.NewReader(`{"message":"lamp"}`))
			req = req.WithContext(context.WithValue(req.Context(), ctxKeyLog{}, logrus.New()))
			rec := httptest.NewRecorder()

			fe.chatBotHandler(rec, req)

			if !tb.closed.Load() {
				t.Fatalf("expected upstream response body to be closed")
			}
			if rec.Code != tc.expectedStatus {
				t.Fatalf("expected HTTP %d, got %d", tc.expectedStatus, rec.Code)
			}
			if tc.expectedReply != "" {
				if ct := rec.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
					t.Fatalf("expected application/json Content-Type, got %q", ct)
				}
				var got struct {
					Message string `json:"message"`
				}
				if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
					t.Fatalf("failed to decode response JSON: %v", err)
				}
				if got.Message != tc.expectedReply {
					t.Fatalf("expected message %q, got %q", tc.expectedReply, got.Message)
				}
			}
		})
	}
}
