"""
MinIO 文件存储客户端 (minio_client.py)

封装 MinIO 对象存储的上传/下载/列举操作。

设计要点：
  - 支持 minio:// 协议 URL 到实际文件路径的解析
  - 支持本地文件系统回退（当 MinIO 不可用时）
  - 统一异常处理

使用方式：
    from ai_engine.parse.minio_client import MinioClient

    client = MinioClient()
    url = client.upload_file("local/path.pdf", bucket="parse-files")
    local_path = client.download_file(url)
"""

import os
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ai_engine.core.config import settings


class MinioClient:
    """
    MinIO 对象存储客户端。

    封装上传、下载、URL 解析等操作：
      - 连接 MinIO 服务端（配置从 settings/环境变量读取）
      - 上传本地文件到指定 bucket
      - 下载 minio:// 协议文件到本地临时目录
      - 服务不可用时自动回退到本地文件系统
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: bool = False,
    ):
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._secure = secure
        self._client = None

    # ======================================================================
    # 属性（惰性初始化）
    # ======================================================================

    @property
    def endpoint(self) -> str:
        if self._endpoint:
            return self._endpoint
        return os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")

    @property
    def access_key(self) -> str:
        if self._access_key:
            return self._access_key
        return os.getenv("MINIO_ACCESS_KEY", "minioadmin")

    @property
    def secret_key(self) -> str:
        if self._secret_key:
            return self._secret_key
        return os.getenv("MINIO_SECRET_KEY", "minioadmin")

    @property
    def bucket(self) -> str:
        return os.getenv("MINIO_BUCKET", "parse-files")

    # ======================================================================
    # 连接管理
    # ======================================================================

    def _get_client(self):
        """惰性初始化 MinIO 客户端。"""
        if self._client is None:
            try:
                from minio import Minio

                self._client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self._secure,
                )
                # 确保 bucket 存在
                if not self._client.bucket_exists(self.bucket):
                    self._client.make_bucket(self.bucket)
            except ImportError:
                raise ImportError("需要 minio 库: pip install minio")
            except Exception as e:
                raise ConnectionError(f"MinIO 连接失败: {e}")
        return self._client

    @property
    def available(self) -> bool:
        """检查 MinIO 服务是否可用。"""
        try:
            client = self._get_client()
            client.bucket_exists(self.bucket)
            return True
        except Exception:
            return False

    # ======================================================================
    # 上传
    # ======================================================================

    def upload_file(
        self,
        local_path: str,
        target_name: Optional[str] = None,
        bucket: Optional[str] = None,
    ) -> str:
        """
        上传本地文件到 MinIO。

        Args:
            local_path:  本地文件路径。
            target_name: MinIO 中的对象名（默认使用文件名）。
            bucket:      MinIO bucket（默认使用 settings 中配置）。

        Returns:
            str: minio:// 协议的 URL。

        Raises:
            FileNotFoundError: 本地文件不存在。
            ConnectionError:   MinIO 不可用时的回退（返回本地路径）。
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"文件未找到: {local_path}")

        bucket = bucket or self.bucket
        target_name = target_name or os.path.basename(local_path)

        try:
            client = self._get_client()
            client.fput_object(bucket, target_name, local_path)
            return f"minio://{bucket}/{target_name}"
        except Exception as e:
            # 回退：返回本地路径
            return local_path

    # ======================================================================
    # 下载
    # ======================================================================

    def download_file(self, file_url: str, target_dir: Optional[str] = None) -> str:
        """
        下载 minio:// 协议文件到本地。

        如果是本地路径（非 minio://），直接返回原路径。

        Args:
            file_url:    minio:// 协议 URL 或本地路径。
            target_dir:  下载目标目录（默认临时目录）。

        Returns:
            str: 下载后的本地文件路径。
        """
        # 本地路径直接返回
        if not file_url.startswith("minio://"):
            return file_url

        parsed = urlparse(file_url)
        bucket = parsed.netloc
        object_name = parsed.path.lstrip("/")

        target_dir = target_dir or tempfile.mkdtemp(prefix="minio_")
        local_path = os.path.join(target_dir, os.path.basename(object_name))

        try:
            client = self._get_client()
            client.fget_object(bucket, object_name, local_path)
            return local_path
        except Exception as e:
            raise ConnectionError(f"MinIO 下载失败: {file_url} — {e}")

    # ======================================================================
    # 列举
    # ======================================================================

    def list_files(self, bucket: Optional[str] = None, prefix: str = "") -> list[str]:
        """列举 bucket 中的文件列表。"""
        bucket = bucket or self.bucket
        try:
            client = self._get_client()
            objects = client.list_objects(bucket, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects if obj.object_name]
        except Exception as e:
            raise ConnectionError(f"MinIO 列举失败: {e}")
