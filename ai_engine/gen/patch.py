"""
节点修补模块 — S4 个性化满足

职责：
  按命令序列修改节点树（update / swap / add / delete / merge / split）

流程：
  command_parser 产生的命令 → node_patcher.apply() → 新节点树 + 变更摘要
"""

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from .commands import EditCommand, CommandType


@dataclass
class PatchResult:
    """修补结果"""
    nodes: list[dict[str, Any]] = field(default_factory=list)
    changes: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class NodePatcher:
    """节点修补器：应用编辑命令到节点树"""

    def apply(self, nodes: list[dict[str, Any]], commands: list[EditCommand],
              regenerate_fn=None) -> PatchResult:
        """应用一系列命令到节点树

        Args:
            nodes: 原始节点数组
            commands: 标准化命令列表（来自 CommandParser）
            regenerate_fn: 可选，部分重生成回调 (node_id, node) → new_node

        Returns:
            PatchResult(修改后的节点树 + 变更记录 + 错误)
        """
        result_nodes = copy.deepcopy(nodes)
        changes = []
        errors = []
        valid_ids = {n["node_id"] for n in result_nodes}

        for cmd in commands:
            handler = self._get_handler(cmd.type)
            try:
                cmd_result = handler(result_nodes, cmd, valid_ids, regenerate_fn)
                if cmd_result.get("error"):
                    errors.append(cmd_result["error"])
                else:
                    result_nodes = cmd_result.get("nodes", result_nodes)
                    if cmd_result.get("change"):
                        changes.append(cmd_result["change"])
                    # 更新有效 ID 集合
                    valid_ids = {n["node_id"] for n in result_nodes}
            except Exception as e:
                errors.append(f"执行 {cmd.type} 失败: {e}")

        return PatchResult(nodes=result_nodes, changes=changes, errors=errors)

    def _get_handler(self, cmd_type: CommandType):
        handlers = {
            CommandType.UPDATE_NODE: self._handle_update,
            CommandType.SWAP_NODES: self._handle_swap,
            CommandType.ADD_NODE: self._handle_add,
            CommandType.DELETE_NODE: self._handle_delete,
            CommandType.CHANGE_TEMPLATE: self._handle_change_template,
            CommandType.MERGE_NODES: self._handle_merge,
            CommandType.SPLIT_NODE: self._handle_split,
        }
        return handlers.get(cmd_type, lambda *a: {"error": f"不支持的命令: {cmd_type}"})

    def _handle_update(self, nodes: list, cmd: EditCommand, valid_ids: set,
                       regenerate_fn) -> dict:
        """更新节点内容"""
        node_id = cmd.params.get("node_id", "")
        if node_id not in valid_ids:
            return {"error": f"节点 {node_id} 不存在"}
        for node in nodes:
            if node["node_id"] == node_id:
                old_content = copy.deepcopy(node)
                # 应用更新参数
                for key, value in cmd.params.items():
                    if key != "node_id" and value is not None:
                        node[key] = value
                # 如果提供了重生成函数且命令标记了 regenerate
                if regenerate_fn and cmd.params.get("regenerate"):
                    try:
                        new_node = regenerate_fn(node_id, node)
                        if new_node:
                            # 合并而非整体替换：regenerate_fn（generate_single）只返回
                            # script / segments / point_details 等少数几个 key，直接替换
                            # 会冲掉 type / node_type / key_points / summary / figure /
                            # teaching_plan —— 幻灯片会当场退化成"没有要点、没有图示"，
                            # 而且下一次局部修改还会接着丢别的字段。
                            merged_node = {**node, **new_node}
                            nodes[nodes.index(node)] = merged_node
                            node = merged_node
                    except Exception as e:
                        return {"error": f"重生成节点 {node_id} 失败: {e}"}
                return {
                    "nodes": nodes,
                    "change": {"type": "update", "node_id": node_id,
                               "summary": f"更新节点 {node_id}"},
                }
        return {"error": f"节点 {node_id} 未找到"}

    def _handle_swap(self, nodes: list, cmd: EditCommand, valid_ids: set,
                     regenerate_fn) -> dict:
        """交换两个节点顺序"""
        # canonical 主名 target_node_ids（对齐 schema.py ModifyCommand / Go ModifyCommandItem），
        # 兼容旧键 node_ids/ids（legacy，勿扩散）。
        ids = (cmd.params.get("target_node_ids")
               or cmd.params.get("node_ids") or cmd.params.get("ids") or [])
        if len(ids) < 2:
            return {"error": "swap 需要至少两个节点 ID"}
        id_a, id_b = ids[0], ids[1]
        idx_a = next((i for i, n in enumerate(nodes) if n["node_id"] == id_a), -1)
        idx_b = next((i for i, n in enumerate(nodes) if n["node_id"] == id_b), -1)
        if idx_a == -1 or idx_b == -1:
            return {"error": f"节点 {id_a} 或 {id_b} 不存在"}
        nodes[idx_a], nodes[idx_b] = nodes[idx_b], nodes[idx_a]
        return {
            "nodes": nodes,
            "change": {"type": "swap", "node_ids": [id_a, id_b],
                       "summary": f"交换节点 {id_a} 和 {id_b}"},
        }

    def _handle_add(self, nodes: list, cmd: EditCommand, valid_ids: set,
                    regenerate_fn) -> dict:
        """新增节点"""
        after_id = cmd.params.get("after_node_id", "")
        content = cmd.params.get("content", "新节点")

        # 解析 node_type：优先使用原生 node_type 字段，其次 type 字段，默认 slide
        raw_type = cmd.params.get("node_type") or cmd.params.get("type", "slide")
        node_type_map = {
            "slide": "SLIDE", "section": "SECTION", "quiz": "QUIZ",
            "interactive": "INTERACTIVE", "cover": "COVER", "divider": "DIVIDER",
        }
        node_type_val = node_type_map.get(raw_type, "SLIDE")

        new_node = {
            # 基础标识
            "node_id": cmd.params.get("node_id", f"node_{len(nodes) + 1:03d}"),
            "title": cmd.params.get("title", content[:20] if isinstance(content, str) else "新节点"),
            "summary": content if isinstance(content, str) else str(content),
            "content": content,
            # 原生 node_type 字段（枚举字符串形式）
            "node_type": node_type_val,
            # 渲染 type 字段（与 node_type 保持一致）
            "type": raw_type,
            # 业务扩展字段（key_points/core_points 对齐）
            "key_points": [],
            "core_points": cmd.params.get("core_points", []),
            "segments": [],
            "questions": [],
            # 排版元数字段
            "layout_hint": None,
            "font_size_hint": None,
            "text_alignment": None,
            "slide_background": None,
            # 完整字段补齐
            "page_ref": None,
            "source_chunk_ids": [],
            "examples": [],
            "key_difficulties": [],
            "expected_outcomes": [],
            "estimated_duration_minutes": 5.0,
            "interactive_questions": [],
            "citation_refs": [],
            "next_node_id": None,
            "prev_node_id": None,
            "metadata": {},
            "source_span": "",
            "prerequisites": [],
        }
        if after_id:
            idx = next((i for i, n in enumerate(nodes) if n["node_id"] == after_id), -1)
            if idx == -1:
                return {"error": f"参考节点 {after_id} 不存在"}
            nodes.insert(idx + 1, new_node)
        else:
            nodes.append(new_node)
        return {
            "nodes": nodes,
            "change": {"type": "add", "node_id": new_node["node_id"],
                       "summary": f"新增节点 {new_node['node_id']}"},
        }

    def _handle_delete(self, nodes: list, cmd: EditCommand, valid_ids: set,
                       regenerate_fn) -> dict:
        """删除节点"""
        node_id = cmd.params.get("node_id", "")
        if node_id not in valid_ids:
            return {"error": f"节点 {node_id} 不存在"}
        nodes[:] = [n for n in nodes if n["node_id"] != node_id]
        return {
            "nodes": nodes,
            "change": {"type": "delete", "node_id": node_id,
                       "summary": f"删除节点 {node_id}"},
        }

    def _handle_change_template(self, nodes: list, cmd: EditCommand, valid_ids: set,
                                regenerate_fn) -> dict:
        """切换模板（仅记录，实际模板切换在预览/导出阶段）"""
        template_id = cmd.params.get("template_id") or cmd.params.get("raw_match", [""])[0]
        return {
            "nodes": nodes,
            "change": {"type": "change_template", "template_id": str(template_id),
                       "summary": f"切换模板为 {template_id}"},
        }

    def _handle_merge(self, nodes: list, cmd: EditCommand, valid_ids: set,
                      regenerate_fn) -> dict:
        """合并多个节点"""
        ids = (cmd.params.get("target_node_ids")
               or cmd.params.get("node_ids") or cmd.params.get("raw_match", []))
        if isinstance(ids, str):
            ids = [ids]
        if len(ids) < 2:
            return {"error": "merge 需要至少两个节点"}
        merged_title = " + ".join(
            next((n.get("title", n["node_id"]) for n in nodes if n["node_id"] == nid), nid)
            for nid in ids
        )
        merged_content = ""
        merged_node = None
        for nid in ids:
            for node in nodes:
                if node["node_id"] == nid:
                    merged_content += (node.get("content") or node.get("script") or "") + "\n"
                    if merged_node is None:
                        merged_node = copy.deepcopy(node)
                        merged_node["node_id"] = f"merged_{'_'.join(ids[:3])}"
                        merged_node["title"] = merged_title[:50]
                    break
        if merged_node:
            merged_node["content"] = merged_content.strip()
            merged_node["script"] = merged_content.strip()
            merged_node["prerequisites"] = []
            nodes[:] = [n for n in nodes if n["node_id"] not in ids]
            nodes.insert(0, merged_node)
            return {
                "nodes": nodes,
                "change": {"type": "merge", "node_ids": ids,
                           "summary": f"合并节点 {', '.join(ids[:3])}"},
            }
        return {"error": "无法合并: 未找到有效节点"}

    def _handle_split(self, nodes: list, cmd: EditCommand, valid_ids: set,
                      regenerate_fn) -> dict:
        """拆分节点"""
        node_id = cmd.params.get("node_id", "")
        split_point = cmd.params.get("split_point", 0)
        try:
            split_point = int(split_point)
        except (ValueError, TypeError):
            split_point = 0
        if node_id not in valid_ids:
            return {"error": f"节点 {node_id} 不存在"}
        for node in nodes:
            if node["node_id"] == node_id:
                content = node.get("content") or node.get("script") or ""
                if not content or split_point <= 0 or split_point >= len(content):
                    return {"error": "无法拆分: 拆分点无效或内容为空"}
                part1 = content[:split_point].strip()
                part2 = content[split_point:].strip()
                if not part1 or not part2:
                    return {"error": "拆分后某部分为空"}
                node["content"] = part1
                node["script"] = part1
                new_id = f"{node_id}_split"
                new_node = copy.deepcopy(node)
                new_node["node_id"] = new_id
                new_node["title"] = f"{node.get('title', '')}-续"
                new_node["content"] = part2
                new_node["script"] = part2
                nodes.insert(nodes.index(node) + 1, new_node)
                return {
                    "nodes": nodes,
                    "change": {"type": "split", "node_id": node_id, "new_node_id": new_id,
                               "summary": f"拆分节点 {node_id}"},
                }
        return {"error": f"节点 {node_id} 未找到"}
