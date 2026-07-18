package config

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/viper"
)

const configFileEnv = "APP_CONFIG_FILE"

type Config struct {
	Server   ServerConfig   `mapstructure:"server"`
	Database DatabaseConfig `mapstructure:"database"`
	Redis    RedisConfig    `mapstructure:"redis"`
	OSS      OSSConfig      `mapstructure:"oss"`
	AI       AIConfig       `mapstructure:"ai"`
	Log      LogConfig      `mapstructure:"log"`
}

type ServerConfig struct {
	Port         int           `mapstructure:"port"`
	Mode         string        `mapstructure:"mode"`
	ReadTimeout  time.Duration `mapstructure:"read_timeout"`
	WriteTimeout time.Duration `mapstructure:"write_timeout"`
}

type DatabaseConfig struct {
	Driver       string `mapstructure:"driver"`
	Host         string `mapstructure:"host"`
	Port         int    `mapstructure:"port"`
	User         string `mapstructure:"user"`
	Password     string `mapstructure:"password"`
	DBName       string `mapstructure:"dbname"`
	SSLMode      string `mapstructure:"sslmode"`
	MaxIdleConns int    `mapstructure:"max_idle_conns"`
	MaxOpenConns int    `mapstructure:"max_open_conns"`
}

func (c DatabaseConfig) DSN() string {
	return fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
		c.Host, c.Port, c.User, c.Password, c.DBName, c.SSLMode)
}

type RedisConfig struct {
	Host     string `mapstructure:"host"`
	Port     int    `mapstructure:"port"`
	Password string `mapstructure:"password"`
	DB       int    `mapstructure:"db"`
	PoolSize int    `mapstructure:"pool_size"`
}

func (c RedisConfig) Addr() string {
	return fmt.Sprintf("%s:%d", c.Host, c.Port)
}

type OSSConfig struct {
	Provider  string `mapstructure:"provider"`
	Endpoint  string `mapstructure:"endpoint"`
	AccessKey string `mapstructure:"access_key"`
	SecretKey string `mapstructure:"secret_key"`
	Bucket    string `mapstructure:"bucket"`
	UseSSL    bool   `mapstructure:"use_ssl"`
}

type AIConfig struct {
	Provider    string        `mapstructure:"provider"`
	BaseURL     string        `mapstructure:"base_url"`
	APIKey      string        `mapstructure:"api_key"`
	Model       string        `mapstructure:"model"`
	Timeout     time.Duration `mapstructure:"timeout"`
	UseDify     bool          `mapstructure:"use_dify"`
	DifyBaseURL string        `mapstructure:"dify_base_url"`
	DifyAPIKey  string        `mapstructure:"dify_api_key"`
}

type LogConfig struct {
	Level      string `mapstructure:"level"`
	Filename   string `mapstructure:"filename"`
	MaxSize    int    `mapstructure:"max_size"`
	MaxBackups int    `mapstructure:"max_backups"`
	MaxAge     int    `mapstructure:"max_age"`
}

func LoadConfig(path string) (*Config, error) {
	v := viper.New()
	v.SetConfigType("yaml")
	setDefaults(v)
	if err := loadEnvFiles(path); err != nil {
		return nil, err
	}
	bindEnv(v)

	configFiles, err := resolveConfigFiles(path)
	if err != nil {
		return nil, err
	}

	if err := mergeConfigFiles(v, configFiles); err != nil {
		return nil, err
	}

	var config Config
	if err := v.Unmarshal(&config); err != nil {
		return nil, fmt.Errorf("解析配置失败: %w", err)
	}

	return &config, nil
}

func setDefaults(v *viper.Viper) {
	v.SetDefault("server.port", 18080)
	v.SetDefault("server.mode", "debug")
	v.SetDefault("server.read_timeout", "30s")
	v.SetDefault("server.write_timeout", "30s")

	v.SetDefault("database.driver", "postgres")
	v.SetDefault("database.host", "localhost")
	v.SetDefault("database.port", 5432)
	v.SetDefault("database.user", "postgres")
	v.SetDefault("database.password", "123456")
	v.SetDefault("database.dbname", "teaching")
	v.SetDefault("database.sslmode", "disable")
	v.SetDefault("database.max_idle_conns", 10)
	v.SetDefault("database.max_open_conns", 50)

	v.SetDefault("redis.host", "localhost")
	v.SetDefault("redis.port", 6379)
	v.SetDefault("redis.password", "")
	v.SetDefault("redis.db", 0)
	v.SetDefault("redis.pool_size", 10)

	v.SetDefault("oss.provider", "minio")
	v.SetDefault("oss.endpoint", "localhost:9000")
	v.SetDefault("oss.access_key", "minioadmin")
	v.SetDefault("oss.secret_key", "minioadmin")
	v.SetDefault("oss.bucket", "teaching")
	v.SetDefault("oss.use_ssl", false)

	v.SetDefault("ai.provider", "llm")
	v.SetDefault("ai.base_url", "http://127.0.0.1:8000")
	v.SetDefault("ai.api_key", "")
	v.SetDefault("ai.model", "")
	v.SetDefault("ai.timeout", "30s")
	v.SetDefault("ai.use_dify", false)
	v.SetDefault("ai.dify_base_url", "http://127.0.0.1:18001")
	v.SetDefault("ai.dify_api_key", "")

	v.SetDefault("log.level", "info")
	v.SetDefault("log.filename", "logs/app.log")
	v.SetDefault("log.max_size", 100)
	v.SetDefault("log.max_backups", 3)
	v.SetDefault("log.max_age", 30)
}

func bindEnv(v *viper.Viper) {
	v.SetEnvPrefix("APP")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()

	bindings := map[string][]string{
		"server.port":       {"SERVER_PORT"},
		"server.mode":       {"SERVER_MODE"},
		"database.host":     {"DB_HOST", "DATABASE_HOST"},
		"database.port":     {"DB_PORT", "DATABASE_PORT"},
		"database.user":     {"DB_USER", "DATABASE_USER"},
		"database.password": {"DB_PASSWORD", "DATABASE_PASSWORD"},
		"database.dbname":   {"DB_NAME", "DATABASE_NAME"},
		"database.sslmode":  {"DB_SSLMODE", "DATABASE_SSLMODE"},
		"redis.host":        {"REDIS_HOST"},
		"redis.port":        {"REDIS_PORT"},
		"redis.password":    {"REDIS_PASSWORD"},
		"redis.db":          {"REDIS_DB"},
		"oss.provider":      {"OSS_PROVIDER"},
		"oss.endpoint":      {"MINIO_ENDPOINT", "OSS_ENDPOINT"},
		"oss.access_key":    {"MINIO_ACCESS_KEY", "OSS_ACCESS_KEY"},
		"oss.secret_key":    {"MINIO_SECRET_KEY", "OSS_SECRET_KEY"},
		"oss.bucket":        {"MINIO_BUCKET", "OSS_BUCKET"},
		"oss.use_ssl":       {"MINIO_USE_SSL", "OSS_USE_SSL"},
		// 后端优先使用本地 AI 引擎地址，再回退到通用 AI_BASE_URL。
		"ai.base_url":  {"AI_ENGINE_BASE_URL", "AI_BASE_URL"},
		"ai.api_key":   {"AI_API_KEY"},
		"ai.model":     {"AI_MODEL"},
		"log.level":    {"LOG_LEVEL"},
		"log.filename": {"LOG_FILENAME"},
	}

	for key, envVars := range bindings {
		bindArgs := append([]string{key}, envVars...)
		_ = v.BindEnv(bindArgs...)
	}
}

func resolveConfigFiles(path string) ([]string, error) {
	configDir := path
	selectedFile := strings.TrimSpace(os.Getenv(configFileEnv))
	if selectedFile == "" {
		selectedFile = strings.TrimSpace(os.Getenv("CONFIG_FILE"))
	}

	if selectedFile != "" {
		resolved := selectedFile
		if !filepath.IsAbs(resolved) {
			resolved = filepath.Join(configDir, resolved)
		}
		if !fileExists(resolved) {
			return nil, fmt.Errorf("读取配置文件失败: 未找到指定配置文件 %s", resolved)
		}
		return []string{resolved}, nil
	}

	configFiles := make([]string, 0, 3)
	for _, name := range []string{"config.yaml.example", "config.yaml", "config.local.yaml"} {
		candidate := filepath.Join(configDir, name)
		if fileExists(candidate) {
			configFiles = append(configFiles, candidate)
		}
	}

	// 如果没有找到任何配置文件，不将其视为致命错误。
	// 允许通过环境变量（或默认值）直接启动。
	if len(configFiles) == 0 {
		return []string{}, nil
	}

	return configFiles, nil
}

func mergeConfigFiles(v *viper.Viper, configFiles []string) error {
	for index, configFile := range configFiles {
		v.SetConfigFile(configFile)
		var err error
		if index == 0 {
			err = v.ReadInConfig()
		} else {
			err = v.MergeInConfig()
		}
		if err != nil {
			return fmt.Errorf("读取配置文件失败: %w", err)
		}
	}

	return nil
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return !info.IsDir()
}

func loadEnvFiles(configDir string) error {
	for _, envFile := range envFileCandidates(configDir) {
		if !fileExists(envFile) {
			continue
		}
		if err := loadEnvFile(envFile); err != nil {
			return err
		}
	}
	return nil
}

func envFileCandidates(configDir string) []string {
	backendRoot := filepath.Dir(configDir)
	workspaceRoot := filepath.Dir(backendRoot)

	// 优先检查 backend 根目录下的 env 文件（方便测试在 backend 下放置 .env.local），
	// 然后再回退到 workspace 根目录下的 env 文件。
	return []string{
		filepath.Join(backendRoot, ".env"),
		filepath.Join(backendRoot, ".env.local"),
		filepath.Join(workspaceRoot, ".env"),
		filepath.Join(workspaceRoot, ".env.local"),
	}
}

func loadEnvFile(path string) error {
	file, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("读取环境变量文件失败: %w", err)
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	lineNo := 0
	for scanner.Scan() {
		lineNo++
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "export ") {
			line = strings.TrimSpace(strings.TrimPrefix(line, "export "))
		}

		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return fmt.Errorf("读取环境变量文件失败: %s 第 %d 行格式不正确", path, lineNo)
		}

		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		value = strings.Trim(value, `"'`)
		if key == "" {
			return fmt.Errorf("读取环境变量文件失败: %s 第 %d 行缺少变量名", path, lineNo)
		}
		if _, exists := os.LookupEnv(key); exists {
			continue
		}
		if err := os.Setenv(key, value); err != nil {
			return fmt.Errorf("读取环境变量文件失败: %w", err)
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("读取环境变量文件失败: %w", err)
	}

	return nil
}
