package oss

import (
	"context"
	"fmt"
	"io"
	"net/url"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"

	"smart-teaching-backend/pkg/config"
)

type MinioClient struct {
	client   *minio.Client
	bucket   string
	endpoint string
	useSSL   bool
}

func NewMinioClient(cfg *config.OSSConfig) (*MinioClient, error) {
	endpoint, useSSL, err := NormalizeEndpoint(cfg.Endpoint, cfg.UseSSL)
	if err != nil {
		return nil, err
	}

	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: useSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("init MinIO client failed: %w", err)
	}

	ctx := context.Background()
	exists, err := client.BucketExists(ctx, cfg.Bucket)
	if err != nil {
		return nil, fmt.Errorf("check bucket failed: %w", err)
	}

	if !exists {
		err = client.MakeBucket(ctx, cfg.Bucket, minio.MakeBucketOptions{})
		if err != nil {
			return nil, fmt.Errorf("create bucket failed: %w", err)
		}
	}

	// Ensure bucket is publicly readable (set on every init to handle upgrades)
	policy := `{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":"*","Action":["s3:GetObject"],"Resource":["arn:aws:s3:::` + cfg.Bucket + `/*"]}]}`
	if err := client.SetBucketPolicy(ctx, cfg.Bucket, policy); err != nil {
		return nil, fmt.Errorf("set bucket public policy failed: %w", err)
	}

	return &MinioClient{
		client:   client,
		bucket:   cfg.Bucket,
		endpoint: endpoint,
		useSSL:   useSSL,
	}, nil
}

// NormalizeEndpoint converts a MinIO endpoint into the host:port format expected by the client.
func NormalizeEndpoint(rawEndpoint string, useSSL bool) (string, bool, error) {
	endpoint := strings.TrimSpace(rawEndpoint)
	if endpoint == "" {
		return "", useSSL, fmt.Errorf("endpoint cannot be empty")
	}

	if strings.Contains(endpoint, "://") {
		parsed, err := url.Parse(endpoint)
		if err != nil {
			return "", useSSL, fmt.Errorf("invalid endpoint format: %w", err)
		}
		if parsed.Host == "" {
			return "", useSSL, fmt.Errorf("endpoint missing host")
		}
		if parsed.Path != "" && parsed.Path != "/" {
			return "", useSSL, fmt.Errorf("endpoint should not contain path")
		}

		switch strings.ToLower(parsed.Scheme) {
		case "http":
			useSSL = false
		case "https":
			useSSL = true
		default:
			return "", useSSL, fmt.Errorf("unsupported endpoint scheme: %q", parsed.Scheme)
		}

		endpoint = parsed.Host
	}

	endpoint = strings.TrimSuffix(endpoint, "/")
	return endpoint, useSSL, nil
}

// UploadFile uploads a file and returns a direct public URL.
func (m *MinioClient) UploadFile(ctx context.Context, objectName string, reader io.Reader, size int64, contentType string) (string, error) {
	_, err := m.client.PutObject(ctx, m.bucket, objectName, reader, size, minio.PutObjectOptions{
		ContentType: contentType,
	})
	if err != nil {
		return "", fmt.Errorf("upload failed: %w", err)
	}

	// Return direct public URL (bucket policy is public read, no expiry issues)
	scheme := "http"
	if m.useSSL {
		scheme = "https"
	}
	return fmt.Sprintf("%s://%s/%s/%s", scheme, m.endpoint, m.bucket, objectName), nil
}

// GetFileURL returns a direct public URL for the given object.
func (m *MinioClient) GetFileURL(ctx context.Context, objectName string, expires time.Duration) (string, error) {
	scheme := "http"
	if m.useSSL {
		scheme = "https"
	}
	return fmt.Sprintf("%s://%s/%s/%s", scheme, m.endpoint, m.bucket, objectName), nil
}

// DeleteFile removes a file from the bucket.
func (m *MinioClient) DeleteFile(ctx context.Context, objectName string) error {
	return m.client.RemoveObject(ctx, m.bucket, objectName, minio.RemoveObjectOptions{})
}
