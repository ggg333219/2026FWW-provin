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

	// 初始化MinIO客户端
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: useSSL,
	})
	if err != nil {
		return nil, fmt.Errorf("初始化MinIO失败: %w", err)
	}

	// 检查bucket是否存在，不存在则创建
	ctx := context.Background()
	exists, err := client.BucketExists(ctx, cfg.Bucket)
	if err != nil {
		return nil, fmt.Errorf("检查bucket失败: %w", err)
	}

	if !exists {
		err = client.MakeBucket(ctx, cfg.Bucket, minio.MakeBucketOptions{})
		if err != nil {
			return nil, fmt.Errorf("创建bucket失败: %w", err)
		}

		// 设置bucket策略为公开读
		policy := `{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"AWS":["*"]},"Action":["s3:GetObject"],"Resource":["arn:aws:s3:::` + cfg.Bucket + `/*"]}]}`
		client.SetBucketPolicy(ctx, cfg.Bucket, policy)
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
		return "", useSSL, fmt.Errorf("初始化MinIO失败: endpoint 不能为空")
	}

	if strings.Contains(endpoint, "://") {
		parsed, err := url.Parse(endpoint)
		if err != nil {
			return "", useSSL, fmt.Errorf("初始化MinIO失败: endpoint 格式非法: %w", err)
		}
		if parsed.Host == "" {
			return "", useSSL, fmt.Errorf("初始化MinIO失败: endpoint 缺少 host")
		}
		if parsed.Path != "" && parsed.Path != "/" {
			return "", useSSL, fmt.Errorf("初始化MinIO失败: endpoint 不应包含路径")
		}

		switch strings.ToLower(parsed.Scheme) {
		case "http":
			useSSL = false
		case "https":
			useSSL = true
		default:
			return "", useSSL, fmt.Errorf("初始化MinIO失败: 不支持的 endpoint 协议 %q", parsed.Scheme)
		}

		endpoint = parsed.Host
	}

	endpoint = strings.TrimSuffix(endpoint, "/")
	return endpoint, useSSL, nil
}

// UploadFile 上传文件
func (m *MinioClient) UploadFile(ctx context.Context, objectName string, reader io.Reader, size int64, contentType string) (string, error) {
	// 上传文件
	_, err := m.client.PutObject(ctx, m.bucket, objectName, reader, size, minio.PutObjectOptions{
		ContentType: contentType,
	})
	if err != nil {
		return "", fmt.Errorf("上传文件失败: %w", err)
	}

	// 生成访问URL（7天有效期）
	url, err := m.client.PresignedGetObject(ctx, m.bucket, objectName, 7*24*time.Hour, nil)
	if err != nil {
		// 如果生成预签名URL失败，返回一个基本路径
		scheme := "http"
		if m.useSSL {
			scheme = "https"
		}
		urlStr := fmt.Sprintf("%s://%s/%s/%s", scheme, m.endpoint, m.bucket, objectName)
		return urlStr, nil
	}

	return url.String(), nil
}

// GetFileURL 获取文件访问URL
func (m *MinioClient) GetFileURL(ctx context.Context, objectName string, expires time.Duration) (string, error) {
	url, err := m.client.PresignedGetObject(ctx, m.bucket, objectName, expires, nil)
	if err != nil {
		return "", err
	}
	return url.String(), nil
}

// DeleteFile 删除文件
func (m *MinioClient) DeleteFile(ctx context.Context, objectName string) error {
	return m.client.RemoveObject(ctx, m.bucket, objectName, minio.RemoveObjectOptions{})
}
