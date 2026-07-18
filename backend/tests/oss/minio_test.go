package oss_test

import (
	"testing"

	"smart-teaching-backend/pkg/oss"
)

func TestNormalizeEndpointSupportsURLAndHostPort(t *testing.T) {
	tests := []struct {
		name         string
		input        string
		useSSL       bool
		wantEndpoint string
		wantUseSSL   bool
	}{
		{name: "host-port", input: "localhost:9000", useSSL: false, wantEndpoint: "localhost:9000", wantUseSSL: false},
		{name: "http-url", input: "http://localhost:9000", useSSL: true, wantEndpoint: "localhost:9000", wantUseSSL: false},
		{name: "https-url", input: "https://minio.example.com", useSSL: false, wantEndpoint: "minio.example.com", wantUseSSL: true},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			endpoint, useSSL, err := oss.NormalizeEndpoint(tc.input, tc.useSSL)
			if err != nil {
				t.Fatalf("normalizeEndpoint returned error: %v", err)
			}
			if endpoint != tc.wantEndpoint {
				t.Fatalf("expected endpoint %q, got %q", tc.wantEndpoint, endpoint)
			}
			if useSSL != tc.wantUseSSL {
				t.Fatalf("expected useSSL %v, got %v", tc.wantUseSSL, useSSL)
			}
		})
	}
}

func TestNormalizeEndpointRejectsPath(t *testing.T) {
	_, _, err := oss.NormalizeEndpoint("http://localhost:9000/minio", false)
	if err == nil {
		t.Fatal("expected error for endpoint with path")
	}
}
