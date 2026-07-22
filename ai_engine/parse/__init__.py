"""
ai_engine/parse — S2 多模态解析包

包含文件上传后的全部解析管道：
  - doc_parser:      PDF / PPTX / DOCX 文本+结构解析
  - ocr_engine:      图片 OCR + 版面分析
  - video_processor: 视频关键帧抽取 + ASR 字幕
  - chunk_normalizer: 统一分块标准化 → Chunk 模型
  - material_mapper:  材料-块映射 + 意图关联
  - task_manager:     异步任务调度 + 状态机
  - minio_client:     MinIO 文件存储客户端

遵循开发规范：
  - LLM 调用统一走 ai_engine.core.LLMClient
  - 数据模型引用 ai_engine.core.schema
  - 配置引用 ai_engine.core.settings
"""

from .doc_parser import DocumentParser
from .ocr_engine import OCREngine
from .video_processor import VideoProcessor
from .chunk_normalizer import ChunkNormalizer
from .material_mapper import MaterialMapper
from .task_manager import TaskManager
from .minio_client import MinioClient

__all__ = [
    "DocumentParser",
    "OCREngine",
    "VideoProcessor",
    "ChunkNormalizer",
    "MaterialMapper",
    "TaskManager",
    "MinioClient",
]
