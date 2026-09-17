"""
命令解析模块 — S4 个性化满足

职责：
  接收用户的自然语言/结构化修改命令 → 解析为标准化命令序列

支持命令类型：
  update_node / swap_nodes / add_node / delete_node
  change_template / merge_nodes / split_node

流程：
  教师反馈 → command_parser.parse() → 已验证的命令列表
"""

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CommandType(str, Enum):
    UPDATE_NODE = "update_node"
    SWAP_NODES = "swap_nodes"
    ADD_NODE = "add_node"
    DELETE_NODE = "delete_node"
    CHANGE_TEMPLATE = "change_template"
    MERGE_NODES = "merge_nodes"
    SPLIT_NODE = "split_node"


@dataclass
class EditCommand:
    """标准化编辑命令"""
    type: CommandType
    params: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 1.0  # 结构化命令=1.0, NL 解析=0.5-0.9


@dataclass
class ParseResult:
    """解析结果"""
    commands: list[EditCommand] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    is_structured: bool = False


class CommandParser:
    """教师修改命令解析器"""

    def parse(self, raw_input: str | dict | list) -> ParseResult:
        """统一解析入口

        Args:
            raw_input: 可以是结构化命令（dict/list）或自然语言字符串

        Returns:
            ParseResult(commands=已验证的命令列表, errors=错误信息)
        """
        # 结构化命令
        if isinstance(raw_input, dict):
            return self._parse_single_command(raw_input)
        if isinstance(raw_input, list):
            return self._parse_command_list(raw_input)
        # 自然语言
        if isinstance(raw_input, str):
            return self._parse_natural_language(raw_input)
        return ParseResult(errors=["不支持的输入类型"])

    def _parse_single_command(self, cmd: dict) -> ParseResult:
        try:
            cmd_type = CommandType(cmd.get("type", ""))
            params = {k: v for k, v in cmd.items() if k != "type"}
            return ParseResult(
                commands=[EditCommand(type=cmd_type, params=params, raw_text=json.dumps(cmd, ensure_ascii=False),
                                      confidence=1.0)],
                is_structured=True,
            )
        except (ValueError, KeyError) as e:
            return ParseResult(errors=[f"无法识别的命令类型: {e}"])

    def _parse_command_list(self, cmds: list) -> ParseResult:
        all_commands = []
        errors = []
        for cmd in cmds:
            result = self._parse_single_command(cmd)
            all_commands.extend(result.commands)
            errors.extend(result.errors)
        return ParseResult(commands=all_commands, errors=errors, is_structured=True)

    def _parse_natural_language(self, text: str) -> ParseResult:
        """将自然语言转化为结构化命令"""
        commands = []
        text_lower = text.lower()

        # 关键词 → 命令映射
        rules = [
            (r"(?:把|将|给)(\S+?)(?:改为|改成|修改为|变成|替换为)(\S+)", CommandType.UPDATE_NODE),
            (r"(?:交换|互换|调换|对调)(\S+?)(?:和|与)(\S+)", CommandType.SWAP_NODES),
            (r"(?:在|于)(\S+?)(?:后|前|之后|之前)(?:添加|插入|增加|加入)(\S+)", CommandType.ADD_NODE),
            (r"(?:删除|移除|去掉|删除掉)(\S+)", CommandType.DELETE_NODE),
            (r"(?:换|改为|切换|使用)(\S+?)(?:模板|样式|主题)", CommandType.CHANGE_TEMPLATE),
            (r"(?:合并|组合|整合)(\S+?)(?:和|与)(\S+)", CommandType.MERGE_NODES),
            (r"(?:拆分|分割|分开)(\S+)", CommandType.SPLIT_NODE),
        ]

        for pattern, cmd_type in rules:
            matches = re.findall(pattern, text)
            for m in matches:
                params = {"raw_match": list(m) if isinstance(m, tuple) else [m]}
                commands.append(EditCommand(
                    type=cmd_type, params=params,
                    raw_text=m if isinstance(m, str) else str(m),
                    confidence=0.7,
                ))

        if not commands:
            # 兜底: 作为 update_node 处理（模糊反馈）
            commands.append(EditCommand(
                type=CommandType.UPDATE_NODE,
                params={"content": text, "raw_feedback": True},
                raw_text=text, confidence=0.5,
            ))

        return ParseResult(commands=commands, is_structured=False)

    def validate(self, cmd: EditCommand, valid_node_ids: set[str]) -> list[str]:
        """验证命令是否可执行，返回错误列表"""
        errors = []
        if cmd.type == CommandType.UPDATE_NODE:
            nid = cmd.params.get("node_id", "")
            if nid and nid not in valid_node_ids:
                errors.append(f"节点 {nid} 不存在")
        elif cmd.type == CommandType.SWAP_NODES:
            # canonical 主名 target_node_ids（对齐 schema.py ModifyCommand / Go ModifyCommandItem），
            # 兼容旧键 node_ids/ids（legacy，勿扩散）。
            for key in ("target_node_ids", "node_ids", "ids"):
                ids = cmd.params.get(key, [])
                for nid in ids:
                    if nid not in valid_node_ids:
                        errors.append(f"节点 {nid} 不存在")
        elif cmd.type == CommandType.DELETE_NODE:
            nid = cmd.params.get("node_id", "")
            if nid and nid not in valid_node_ids:
                errors.append(f"节点 {nid} 不存在")
        return errors
