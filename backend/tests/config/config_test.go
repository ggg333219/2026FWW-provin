package config_test

import (
	"os"
	"path/filepath"
	"testing"

	configpkg "smart-teaching-backend/pkg/config"
)

func TestLoadConfigMergesFilesAndEnv(t *testing.T) {
	t.Setenv("MINIO_SECRET_KEY", "env-secret")
	t.Setenv("DB_HOST", "db-from-env")

	configDir := createConfigDir(t)
	writeTestFile(t, filepath.Join(configDir, "config.yaml.example"), `
database:
  host: localhost
oss:
  endpoint: localhost:9000
  secret_key: file-secret
`)
	writeTestFile(t, filepath.Join(configDir, "config.local.yaml"), `
oss:
  endpoint: 192.168.1.8:9000
`)

	cfg, err := configpkg.LoadConfig(configDir)
	if err != nil {
		t.Fatalf("LoadConfig returned error: %v", err)
	}

	if cfg.Database.Host != "db-from-env" {
		t.Fatalf("expected database host from env, got %q", cfg.Database.Host)
	}
	if cfg.OSS.Endpoint != "192.168.1.8:9000" {
		t.Fatalf("expected local override endpoint, got %q", cfg.OSS.Endpoint)
	}
	if cfg.OSS.SecretKey != "env-secret" {
		t.Fatalf("expected secret key from env, got %q", cfg.OSS.SecretKey)
	}
}

func TestLoadConfigSupportsExplicitConfigFile(t *testing.T) {
	configDir := createConfigDir(t)
	explicitFile := filepath.Join(configDir, "config.custom.yaml")
	writeTestFile(t, explicitFile, `
server:
  port: 19090
oss:
  endpoint: docker-minio:9000
`)

	t.Setenv("APP_CONFIG_FILE", explicitFile)

	cfg, err := configpkg.LoadConfig(configDir)
	if err != nil {
		t.Fatalf("LoadConfig returned error: %v", err)
	}

	if cfg.Server.Port != 19090 {
		t.Fatalf("expected server port 19090, got %d", cfg.Server.Port)
	}
	if cfg.OSS.Endpoint != "docker-minio:9000" {
		t.Fatalf("expected explicit file endpoint, got %q", cfg.OSS.Endpoint)
	}
}

func TestLoadConfigLoadsBackendEnvFile(t *testing.T) {
	workspaceRoot := t.TempDir()
	backendRoot := filepath.Join(workspaceRoot, "backend")
	configDir := filepath.Join(backendRoot, "config")
	if err := os.MkdirAll(configDir, 0o755); err != nil {
		t.Fatalf("failed to create config dir: %v", err)
	}

	writeTestFile(t, filepath.Join(configDir, "config.yaml.example"), `
ai:
  base_url: http://127.0.0.1:8000
oss:
  endpoint: localhost:9000
`)
	writeTestFile(t, filepath.Join(backendRoot, ".env.local"), "AI_BASE_URL=http://10.10.10.10:8000\nMINIO_ENDPOINT=10.0.0.20:9000\n")

	cfg, err := configpkg.LoadConfig(configDir)
	if err != nil {
		t.Fatalf("LoadConfig returned error: %v", err)
	}

	if cfg.AI.BaseURL != "http://10.10.10.10:8000" {
		t.Fatalf("expected AI base URL from env file, got %q", cfg.AI.BaseURL)
	}
	if cfg.OSS.Endpoint != "10.0.0.20:9000" {
		t.Fatalf("expected MinIO endpoint from env file, got %q", cfg.OSS.Endpoint)
	}
}

func createConfigDir(t *testing.T) string {
	t.Helper()
	workspaceRoot := t.TempDir()
	configDir := filepath.Join(workspaceRoot, "backend", "config")
	if err := os.MkdirAll(configDir, 0o755); err != nil {
		t.Fatalf("failed to create config dir: %v", err)
	}
	return configDir
}

func writeTestFile(t *testing.T, path string, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("failed to create parent dir for %s: %v", path, err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("failed to write test file %s: %v", path, err)
	}
}
