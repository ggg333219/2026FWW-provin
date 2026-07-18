package handler

import (
    "crypto/aes"
    "crypto/cipher"
    "crypto/rand"
    "encoding/base64"
    "io"
    "os"
    "smart-teaching-backend/pkg/logger"
)

func getDataKey() []byte {
    key := os.Getenv("OPEN_API_DATA_KEY")
    if len(key) == 0 {
        return nil
    }
    return []byte(key)
}

// EncryptString 使用 AES-256-GCM 对字符串进行加密，返回 base64 编码的密文。
// 如果没有配置密钥，将返回原文并记录警告（仅用于开发环境）。
func EncryptString(plain string) string {
    key := getDataKey()
    if key == nil || len(key) != 32 {
        logger.Warn("未配置有效的 OPEN_API_DATA_KEY（32 字节），将以明文存储敏感字段 — 请在生产环境配置密钥！")
        return plain
    }
    block, err := aes.NewCipher(key)
    if err != nil {
        logger.Errorf("创建 AES 密钥失败: %v", err)
        return plain
    }
    gcm, err := cipher.NewGCM(block)
    if err != nil {
        logger.Errorf("创建 GCM 模式失败: %v", err)
        return plain
    }
    nonce := make([]byte, gcm.NonceSize())
    if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
        logger.Errorf("生成随机 nonce 失败: %v", err)
        return plain
    }
    ct := gcm.Seal(nonce, nonce, []byte(plain), nil)
    return base64.StdEncoding.EncodeToString(ct)
}

// DecryptString 解密由 EncryptString 加密的 base64 密文；解密失败时返回原文并记录错误。
func DecryptString(cipherText string) string {
    key := getDataKey()
    if key == nil || len(key) != 32 {
        return cipherText
    }
    data, err := base64.StdEncoding.DecodeString(cipherText)
    if err != nil {
        logger.Errorf("base64 解码失败: %v", err)
        return cipherText
    }
    block, err := aes.NewCipher(key)
    if err != nil {
        logger.Errorf("创建 AES 密钥失败: %v", err)
        return cipherText
    }
    gcm, err := cipher.NewGCM(block)
    if err != nil {
        logger.Errorf("创建 GCM 模式失败: %v", err)
        return cipherText
    }
    nonceSize := gcm.NonceSize()
    if len(data) < nonceSize {
        logger.Errorf("密文长度小于 nonce 大小")
        return cipherText
    }
    nonce, ct := data[:nonceSize], data[nonceSize:]
    plain, err := gcm.Open(nil, nonce, ct, nil)
    if err != nil {
        logger.Errorf("解密失败: %v", err)
        return cipherText
    }
    return string(plain)
}
