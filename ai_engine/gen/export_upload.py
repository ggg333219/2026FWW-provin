"""导出产物 MinIO 上传辅助 (export_upload.py)

职责边界：
  - 导出文件生成成功后，尝试上传到 MinIO 对象存储
  - 配置从环境变量读取（与 .env / parse/minio_client.py 保持同一命名习惯）：
      MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY / MINIO_BUCKET / MINIO_USE_SSL
  - 上传前做 bucket 预检，不存在则自动创建
  - 任何失败都不抛出异常：返回结构化结果，由调用方决定降级策略
    （保留本地路径、任务仍为 done、附 upload_status=failed 与原因）

与 parse/minio_client.py 的差异：
  MinioClient.upload_file 会吞掉所有异常并静默回退本地路径，调用方无法区分
  "已上传" 与 "未上传"。本模块显式区分 uploaded / failed / skipped 三种状态。

minio 包使用延迟导入（函数内 import），未安装时给出友好提示，不阻塞模块加载。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """单文件上传结果。"""
    upload_status: str            # "uploaded" | "failed" | "skipped"
    minio_path: Optional[str]     # 成功时为 minio://bucket/object，失败/跳过为 None
    local_path: str               # 本地文件路径（降级时下载链路仍然可用）
    reason: str = ""              # failed / skipped 时的原因说明

    def to_meta(self) -> dict[str, Any]:
        return {
            "upload_status": self.upload_status,
            "minio_path": self.minio_path,
            "local_path": self.local_path,
            "upload_error": self.reason or None,
        }


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key) or "").strip() or default


def is_minio_configured() -> bool:
    """是否配置了 MinIO endpoint（未配置则直接 skipped，不做无谓重试）。

    注意：这里不提供默认值 —— 只有环境里显式设置了 MINIO_ENDPOINT 才视为
    已配置，否则未部署 MinIO 的环境会把连接错误误记为 failed 而非 skipped。
    """
    return bool((os.getenv("MINIO_ENDPOINT") or "").strip())


def upload_export_file(local_path: str, object_name: str,
                       bucket: Optional[str] = None) -> UploadResult:
    """上传导出产物到 MinIO，失败时返回 failed 而不抛异常。

    Args:
        local_path:  本地导出文件路径（必须已存在）。
        object_name: MinIO 对象名，如 "exports/exp_xxx.pptx"。
        bucket:      目标 bucket，默认读 MINIO_BUCKET（.env 中为 teaching）。

    Returns:
        UploadResult：upload_status ∈ uploaded / failed / skipped。
    """
    if not is_minio_configured():
        reason = "MINIO_ENDPOINT 未配置，跳过上传（本地文件保留，下载链路不受影响）"
        logger.info("[export_upload] skipped: %s (local=%s)", reason, local_path)
        return UploadResult("skipped", None, local_path, reason)

    if not os.path.exists(local_path):
        reason = f"本地文件不存在: {local_path}"
        logger.warning("[export_upload] failed: %s", reason)
        return UploadResult("failed", None, local_path, reason)

    endpoint = _env("MINIO_ENDPOINT")
    access_key = _env("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = _env("MINIO_SECRET_KEY", "minioadmin")
    target_bucket = (bucket or _env("MINIO_BUCKET", "teaching")).strip("/")
    use_ssl = _env("MINIO_USE_SSL", "false").lower() in ("1", "true", "yes")

    # 延迟导入：minio 未安装时给出可执行的修复提示
    try:
        from minio import Minio
    except ImportError:
        reason = "minio Python 包未安装（pip install minio），已降级保留本地文件"
        logger.warning("[export_upload] skipped: %s (local=%s)", reason, local_path)
        return UploadResult("skipped", None, local_path, reason)

    try:
        client = Minio(endpoint, access_key=access_key, secret_key=secret_key,
                       secure=use_ssl)
        # bucket 预检：不存在则自动创建（公开策略不由本模块管理）
        if not client.bucket_exists(target_bucket):
            client.make_bucket(target_bucket)
        client.fput_object(target_bucket, object_name, local_path)
        logger.info("[export_upload] uploaded: minio://%s/%s", target_bucket, object_name)
        return UploadResult("uploaded", f"minio://{target_bucket}/{object_name}",
                            local_path)
    except Exception as exc:  # 网络/认证/权限等任何失败都降级，不阻塞导出主流程
        reason = f"MinIO 上传失败（endpoint={endpoint}, bucket={target_bucket}）: {exc}"
        logger.warning("[export_upload] failed: %s (local=%s)", reason, local_path)
        return UploadResult("failed", None, local_path, reason)
