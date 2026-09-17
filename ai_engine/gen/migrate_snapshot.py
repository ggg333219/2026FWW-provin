"""
旧版本快照 schema 迁移工具 (gen/migrate_snapshot.py)

将 data/versions/ 下历史 TeachingNode 快照迁移为当前 schema 标准，保证：
  1. 缺失字段补齐默认值（list → []，str/数字 → 默认，可选 → None）
  2. questions 若为旧 dict 结构 [{question, answer, type}]，转为当前 list[str] 标准
     （M1-1 已统一 TeachingNode.questions 为 list[str]，旧 dict 快照加载会类型报错）
  3. node_type / type 互补：为空时互相回填；node_type 值规范化为 NodeType 枚举小写
  4. 支持 --dry-run 只预览不改写

用法：
    python ai_engine/gen/migrate_snapshot.py                # 执行迁移
    python ai_engine/gen/migrate_snapshot.py --dry-run      # 只预览
    python ai_engine/gen/migrate_snapshot.py --root <path>  # 指定快照根目录
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# ── 当前 schema 标准字段默认值（与 core/schema.py TeachingNode 对齐）────────────
_STR_LIST_FIELDS = (
    "source_chunk_ids", "core_points", "examples", "key_difficulties",
    "expected_outcomes", "interactive_questions", "citation_refs",
    "key_points", "questions", "prerequisites",
)
_DICT_LIST_FIELDS = ("segments",)
_NULLABLE_FIELDS = (
    "layout_hint", "font_size_hint", "text_alignment", "slide_background",
    "next_node_id", "prev_node_id", "page_ref",
)
_DEFAULT_SCALARS = {
    "node_id": "",
    "title": "",
    "node_type": "slide",
    "type": "",
    "summary": "",
    "content": "",
    "script": "",
    "source_span": "",
    "estimated_duration_minutes": 5.0,
    "metadata": {},
}

# node_type 值规范化映射：旧大写枚举 → NodeType 小写枚举值
_NODE_TYPE_NORMALIZE = {
    "SLIDE": "slide", "SECTION": "section", "QUIZ": "quiz",
    "INTERACTIVE": "interactive", "COVER": "cover", "DIVIDER": "divider",
}


def _normalize_questions(value: Any) -> list[str]:
    """旧 questions 可能为 list[dict{question,answer,type}]，统一转为 list[str]。"""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            text = item.get("question") or item.get("content") or item.get("text")
            if isinstance(text, str) and text.strip():
                result.append(text.strip())
        elif item is not None:
            result.append(str(item))
    return result


def migrate_node(node: dict[str, Any]) -> dict[str, Any]:
    """将单个节点迁移为当前 schema 标准（原地补齐，保留未知字段）。"""
    out = dict(node)

    # 1. 字符串列表字段 → 确保是 list[str]
    for field in _STR_LIST_FIELDS:
        value = out.get(field)
        if not isinstance(value, list):
            out[field] = []
        elif field == "questions":
            # questions 特殊处理：dict → str 转换
            out[field] = _normalize_questions(value)
        else:
            out[field] = [str(v) for v in value if v is not None]

    # 2. 结构体列表字段 → 确保是 list[dict]
    for field in _DICT_LIST_FIELDS:
        value = out.get(field)
        out[field] = [dict(v) for v in value if isinstance(v, dict)] if isinstance(value, list) else []

    # 3. 可空字段 → 缺失时补 None
    for field in _NULLABLE_FIELDS:
        if field not in out:
            out[field] = None

    # 4. 标量默认值字段 → 缺失时补默���
    for field, default in _DEFAULT_SCALARS.items():
        if field not in out:
            out[field] = default

    # 5. node_type / type 互补
    node_type = out.get("node_type") or out.get("type") or "slide"
    # 枚举值规范化：大写枚举 → 小写（TeachingNode.node_type 是 NodeType 枚举）
    normalized_nt = _NODE_TYPE_NORMALIZE.get(str(node_type), str(node_type).lower())
    out["node_type"] = normalized_nt
    # type 字段优先用原始 type，其次回填 node_type 值
    if not out.get("type"):
        out["type"] = normalized_nt

    return out


def migrate_file(filepath: Path, dry_run: bool = False) -> bool:
    """迁移单个快照文件。返回是否有改动（或 dry-run 下是否会有改动）。"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    nodes = data.get("nodes_snapshot") or []
    new_nodes: list[dict[str, Any]] = []
    for node in nodes:
        new_nodes.append(migrate_node(dict(node)) if isinstance(node, dict) else node)

    original_str = json.dumps(data, ensure_ascii=False, default=str)
    if new_nodes:
        data["nodes_snapshot"] = new_nodes
    migrated_str = json.dumps(data, ensure_ascii=False, default=str)

    if migrated_str == original_str:
        return False
    if not dry_run:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="旧版本快照 schema 迁移工具")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不实际写入")
    parser.add_argument("--root", type=str, default="data/versions",
                        help="快照根目录（默认 data/versions）")
    args = parser.parse_args(argv)

    base = Path(args.root)
    if not base.is_dir():
        print(f"快照目录不存在: {base}")
        return 0

    mode = "预览" if args.dry_run else "迁移"
    migrated = 0
    for ver_dir in sorted(base.iterdir()):
        if not ver_dir.is_dir():
            continue
        for snap_file in sorted(ver_dir.glob("v_*.json")):
            try:
                if migrate_file(snap_file, dry_run=args.dry_run):
                    tag = "需迁移" if args.dry_run else "已迁移"
                    print(f"  [{tag}] {snap_file}")
                    migrated += 1
            except Exception as e:  # noqa: BLE001
                print(f"   [错误] {snap_file}: {e}")

    print(f"{mode}完成: 共 {migrated} 个文件需要改动")
    if args.dry_run and migrated:
        print("提示: 去掉 --dry-run 后执行实际迁移。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
