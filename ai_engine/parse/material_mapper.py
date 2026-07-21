"""
材料-块映射器 (material_mapper.py)

构建材料（文件）与解析块之间的映射关系，并关联教学意图。

核心产出：
  material_to_chunks: file_id → [chunk_id, ...]
  chunk_to_material:  chunk_id → file_id
  intent_chunks:       intent_id → [chunk_id, ...]（可选）

使用方式：
    from ai_engine.parse.material_mapper import MaterialMapper

    mapper = MaterialMapper()
    mapper.build_mappings(task_id="t1", chunks=[...], intent_id="i1")
    mapping = mapper.get_material_mapping("t1")
"""

import uuid
from typing import Any, Optional

from ai_engine.core.schema import Chunk


class MaterialMapper:
    """
    材料-块映射器。

    管理三种映射关系：
      1. material_to_chunks — 每个文件产生了哪些 Chunk
      2. chunk_to_material  — 每个 Chunk 属于哪个文件
      3. intent_chunks      — 每个意图关联哪些 Chunk（可选）
    """

    def __init__(self):
        # task_id → {"file_ref": [chunk_id, ...]}
        self._material_to_chunks: dict[str, dict[str, list[str]]] = {}

        # chunk_id → file_ref
        self._chunk_to_material: dict[str, str] = {}

        # intent_id → [chunk_id, ...]
        self._intent_chunks: dict[str, list[str]] = {}

    # ======================================================================
    # 写操作
    # ======================================================================

    def build_mappings(
        self,
        task_id: str,
        chunks: list[Chunk],
        intent_id: Optional[str] = None,
    ) -> None:
        """
        根据解析结果构建所有映射关系。

        Args:
            task_id:     解析任务 ID。
            chunks:      标准化后的 Chunk 列表。
            intent_id:   关联的教学意图 ID（可选）。
        """
        if task_id not in self._material_to_chunks:
            self._material_to_chunks[task_id] = {}

        for chunk in chunks:
            source_ref = chunk.source_ref or "unknown"
            chunk_id = chunk.chunk_id

            # 文件 → Chunk
            if source_ref not in self._material_to_chunks[task_id]:
                self._material_to_chunks[task_id][source_ref] = []
            self._material_to_chunks[task_id][source_ref].append(chunk_id)

            # Chunk → 文件
            self._chunk_to_material[chunk_id] = source_ref

        # 意图关联
        if intent_id:
            if intent_id not in self._intent_chunks:
                self._intent_chunks[intent_id] = []
            self._intent_chunks[intent_id].extend(c.chunk_id for c in chunks)

    # ======================================================================
    # 读操作
    # ======================================================================

    def get_material_mapping(self, task_id: str) -> dict[str, list[str]]:
        """
        获取指定 task 的材料 → Chunk 映射。

        Returns:
            {"file_ref": ["chunk_id", ...], ...}
        """
        return self._material_to_chunks.get(task_id, {})

    def get_chunk_source(self, chunk_id: str) -> Optional[str]:
        """查询 Chunk 所属的文件引用。"""
        return self._chunk_to_material.get(chunk_id)

    def get_intent_chunks(self, intent_id: str) -> list[str]:
        """查询意图关联的所有 Chunk ID。"""
        return self._intent_chunks.get(intent_id, [])

    def clear_task(self, task_id: str) -> None:
        """清除指定 task 的映射（用于重试/清理）。"""
        mapping = self._material_to_chunks.pop(task_id, {})
        # 清除对应的 chunk→material 记录
        for chunk_ids in mapping.values():
            for cid in chunk_ids:
                self._chunk_to_material.pop(cid, None)
