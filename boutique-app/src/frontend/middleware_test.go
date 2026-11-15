package main

import (
	"context"
	"net/http"
	"net/http/cookiejar"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/sirupsen/logrus"
)

func TestSessionSurvivesDeepLinkAndLogout(t *testing.T) {
	t.Setenv("ENABLE_SINGLE_SHARED_SESSION", "false")
	originalBase := baseUrl
	t.Cleanup(func() { baseUrl = originalBase })
	for _, prefix := range []string{"", "/shop"} {
		t.Run(prefix, func(t *testing.T) {
			baseUrl = prefix
			jar, err := cookiejar.New(nil)
			if err != nil {
				t.Fatal(err)
			}
			request := func(path string, handler http.Handler) *httptest.ResponseRecorder {
				r := httptest.NewRequest(http.MethodGet, "http://example.test"+prefix+path, nil)
				for _, cookie := range jar.Cookies(r.URL) {
					r.AddCookie(cookie)
				}
				r = r.WithContext(context.WithValue(r.Context(), ctxKeyLog{}, logrus.New()))
				w := httptest.NewRecorder()
				handler.ServeHTTP(w, r)
				jar.SetCookies(r.URL, w.Result().Cookies())
				return w
			}
			var session string
			handler := ensureSessionID(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				session = sessionID(r)
			}))
			request("/product/sku", handler)
			first := session
			if first == "" {
				t.Fatal("missing session")
			}
			for _, path := range []string{"/cart", "/cart/checkout"} {
				request(path, handler)
				if session != first {
					t.Fatalf("session changed at %s", path)
				}
			}
			fe := &frontendServer{}
			currency := request("/setCurrency?currency_code=EUR", http.HandlerFunc(fe.setCurrencyHandler))
			if currency.Code != http.StatusFound {
				t.Fatalf("set currency status: %d", currency.Code)
			}
			request("/cart", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if currentCurrency(r) != "EUR" {
					t.Fatal("currency did not reach cart")
				}
			}))
			logout := request("/logout", http.HandlerFunc(fe.logoutHandler))
			for _, cookie := range logout.Result().Cookies() {
				if cookie.Path != prefix+"/" || cookie.MaxAge != -1 {
					t.Fatalf("incorrect deletion cookie: %v", cookie)
				}
			}
			request("/cart", handler)
			if session == first {
				t.Fatal("logout did not clear session")
			}
			request("/cart", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if currentCurrency(r) != defaultCurrency {
					t.Fatal("logout did not clear currency")
				}
			}))
		})
	}
}

func TestLogoutLeavesUnrelatedCookiesAlone(t *testing.T) {
	r := httptest.NewRequest(http.MethodGet, "http://example.test/logout", nil)
	r.AddCookie(&http.Cookie{Name: "other_app", Value: "keep"})
	r = r.WithContext(context.WithValue(r.Context(), ctxKeyLog{}, logrus.New()))
	w := httptest.NewRecorder()
	(&frontendServer{}).logoutHandler(w, r)
	if strings.Contains(w.Header().Get("Set-Cookie"), "other_app") {
		t.Fatal("logout deleted an unrelated cookie")
	}
}
