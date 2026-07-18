-- 扩宽平台用户联系方式字段，避免加密后的 email/phone 超出 varchar 容量
ALTER TABLE platform_users
    ALTER COLUMN email TYPE varchar(255),
    ALTER COLUMN phone TYPE varchar(255);