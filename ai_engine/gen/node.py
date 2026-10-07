"""
节点生成模块 — S3 课件生成的第二步

职责：
  大纲节点 → LLM 逐节点生成讲稿内容（可并行）

流程：
  节点树 → [GENERATING] → 每个节点产出 script / segments / interactive_questions

现有基础：
  从 generator.py 的 generate_node_script / _run_stage3_scripts 重构而来

LLM 调用：
  统一通过 core.llm.LLMClient，构造函数可注入 llm_client 供测试用。
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from ..schema import (
    build_stage3_script_schema,
    extract_list_payload,
    normalize_stage3_scripts,
    build_enhanced_script_schema,
    normalize_point_details,
    normalize_text_list,
    sanitize_node_type,
    _normalize_optional_text,
)
from ..core.llm import LLMClient

# segment 的 estimated_seconds 约束（与生成 prompt 中 "15-120整数" 的约定一致）
_SEGMENT_SECONDS_DEFAULT = 30
_SEGMENT_SECONDS_MIN = 15
_SEGMENT_SECONDS_MAX = 120


def _plan_constraint(plan: Any) -> str:
    """把教学表达规划器的本页决策，作为**约束**注入讲稿提示词。

    这一页「给学生看什么」在规划阶段已经定了（大字结论 + 图示类型），写稿只能围绕它
    展开。不注入的话会出现最典型的失败：图示讲 A、讲稿讲 B —— 两者各自都通顺，合在
    一页上却互相矛盾。

    规划缺失（老课件 / 规划失败）时返回空串，prompt 与不传时逐字相同。
    """
    if not isinstance(plan, dict):
        return ""
    goal = str(plan.get("teaching_goal") or "").strip()
    conclusion = str(plan.get("key_conclusion") or "").strip()
    note = str(plan.get("teacher_note") or "").strip()
    if not (goal or conclusion or note):
        return ""

    lines = ["【本页教学规划（已定，不得推翻）】"]
    if goal:
        lines.append(f"- 教学目的：{goal}")
    if conclusion:
        lines.append(f"- 本页结论（将作为大字直接显示在幻灯片上）：{conclusion}")
    if note:
        lines.append(f"- 留给教师口头讲：{note}")
    lines.append(
        "- point_details 的展开必须服务于上面这个结论，不要引入与之矛盾的说法，"
        "也不要把结论原样抄一遍。"
    )
    return "\n".join(lines) + "\n"


def _plans_brief(plans: Any, nodes: list[dict[str, Any]]) -> str:
    """把整份课件的逐页规划，拼成批量写稿提示词里的约束块。

    批量写稿是**一次调用生成全部节点**，所以每段约束都必须带上 node_id + 标题 ——
    否则模型分不清哪段属于哪一页，逐页的约束会串成一份全局要求。

    plans 缺失 / 没有任何一页有约束时返回空串，user_prompt 与不传时逐字相同。
    """
    if not isinstance(plans, dict) or not plans:
        return ""
    blocks: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            continue
        constraint = _plan_constraint(plans.get(node_id))
        if not constraint:
            continue
        title = str(node.get("title") or "").strip() or "未命名"
        blocks.append(f"■ {node_id}（{title}）\n{constraint.rstrip()}")
    if not blocks:
        return ""
    return (
        "【各页教学表达约束】以下是对每一页「该怎么教」的决策，"
        "每页的讲稿只围绕它自己那一段展开：\n" + "\n".join(blocks)
    )


def _safe_estimated_seconds(value: Any) -> int:
    """安全转换 segment 的 estimated_seconds（M1-4B P1/P6）。

    - 非数字字符串 / None / 空值 → 默认 30。原实现 `int(x or 30)` 遇 "abc" 这类
      非数字字符串会抛 ValueError，导致 generate_enhanced 整批 except 降级。
    - 浮点截断可接受（int(45.5) == 45）。
    - 0 值语义：生成 prompt 明确约束 estimated_seconds 为 15-120 的整数，0 不是
      合法值，因此不保留 0，统一钳制到 [15, 120]（旧实现 `or 30` 会把 0 改写为
      30，同样不保留 0；新行为为 0 → 15，是显式钳制而非真值短路）。
    """
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        # "45.5" 这类数字字符串先试 int() 失败，再按浮点截断
        try:
            seconds = int(float(value))
        except (TypeError, ValueError):
            return _SEGMENT_SECONDS_DEFAULT
    return max(_SEGMENT_SECONDS_MIN, min(_SEGMENT_SECONDS_MAX, seconds))


def _normalize_single_segments(raw: Any, node_id: str) -> list[dict]:
    """规整 generate_single 拿到的 segments（单节点路径）。

    逐段校验规则与 `_normalize_enhanced_scripts` 同源：非 dict 跳过、缺 text 跳过、
    segment_type / 时长给默认值。两处差别：

      - segment_id 缺失时按序号补 `seg_001` 形态。整批生成里 node_id 可能串台，
        所以那里缺 id 宁可丢弃；单节点只有一个 node_id，补号不会产生歧义，
        为了一颗漏写的 id 丢掉整段内容不划算。
      - node_id 一律用本节点的权威值覆盖，避免模型自创 id（prompt 明令禁止）。
    """
    if not isinstance(raw, list):
        return []
    segments: list[dict] = []
    for index, seg in enumerate(raw, start=1):
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        segments.append({
            "segment_id": str(seg.get("segment_id") or "").strip() or f"seg_{index:03d}",
            "text": text,
            "node_id": node_id,
            "segment_type": str(seg.get("segment_type") or "explanation").strip(),
            "estimated_seconds": _safe_estimated_seconds(seg.get("estimated_seconds")),
            "difficulty": str(seg.get("difficulty") or "medium").strip(),
            "interaction_hint": str(seg.get("interaction_hint") or "").strip(),
            "knowledge_card": seg.get("knowledge_card") or {},
        })
    return segments


@dataclass
class NodeGenConfig:
    """节点生成配置"""
    model: str = ""
    temperature: float = 0.2
    max_content_chars: int = 3500


class NodeGenerator:
    """根据节点树逐节点生成讲稿内容"""

    def __init__(self, config: NodeGenConfig | None = None, llm_client: Optional[LLMClient] = None):
        self.config = config or NodeGenConfig()
        self._llm = llm_client  # 可注入，供测试用

    # ── 公开入口 ──

    def generate_all(self, nodes: list[dict[str, Any]],
                     context_markdown: str = "",
                     course_name: str | None = None,
                     plans: Optional[dict[str, Any]] = None,
                     generation_instruction_set: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """生成所有节点的讲稿。整批失败时按节点降级重试，避免整批退兜底。

        plans: 教学表达规划器的逐页决策 ``{node_id: plan}``，作为**约束**注入写稿
        提示词。可选 —— 缺席时 prompt 与不传时逐字相同（老课件 / 规划失败）。
        """
        fallback = self._fallback_scripts(nodes, course_name)
        node_ids = {n["node_id"] for n in nodes}
        plans = plans if isinstance(plans, dict) else {}
        instruction_context = self._generation_instruction_context(generation_instruction_set)
        try:
            scripts = self._run_batch_generation(context_markdown, nodes, course_name, plans, instruction_context)
            if not scripts:
                scripts = fallback["scripts"]
            scripts = normalize_stage3_scripts(scripts, node_ids)
            return {"scripts": scripts or fallback["scripts"], "used_fallback": False}
        except Exception:
            # 整批失败 → 逐节点降级重试，仍失败的节点才用单节点兜底。
            # 降级路径传 max_attempts=1（不重试）：整批已重试过，逐节点再各自
            # 重试会把最坏延迟放大为 N × (timeout + 退避)。
            scripts = []
            for node in nodes:
                scripts.append(self.generate_single(
                    node, course_name, max_attempts=1,
                    teaching_plan=plans.get(str(node.get("node_id") or "")),
                    generation_instruction_context=instruction_context,
                ))
            scripts = normalize_stage3_scripts(scripts, node_ids)
            return {"scripts": scripts or fallback["scripts"], "used_fallback": True}

    def generate_enhanced(self, nodes: list[dict[str, Any]],
                          context_markdown: str = "",
                          course_name: str | None = None,
                          plans: Optional[dict[str, Any]] = None,
                          generation_instruction_set: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """增强版生成：带 segment_type / estimated_seconds / interaction_hint / knowledge_card。
        整批失败时按节点降级重试，避免整批退兜底。

        plans 同 :meth:`generate_all`。
        """
        fallback = self._enhanced_fallback(nodes, course_name)
        node_ids = {n["node_id"] for n in nodes}
        plans = plans if isinstance(plans, dict) else {}
        instruction_context = self._generation_instruction_context(generation_instruction_set)
        try:
            scripts = self._run_enhanced_batch(context_markdown, nodes, course_name, plans, instruction_context)
            if not scripts:
                scripts = fallback["scripts"]
            scripts = self._normalize_enhanced_scripts(scripts, node_ids)
            return {"scripts": scripts or fallback["scripts"], "used_fallback": False}
        except Exception:
            # 整批失败 → 逐节点降级重试，仍失败的节点才用单节点兜底
            # （max_attempts=1 不重试，避免最坏延迟 N × (timeout + 退避)）
            scripts = []
            for node in nodes:
                scripts.append(self.generate_single(
                    node, course_name, max_attempts=1,
                    teaching_plan=plans.get(str(node.get("node_id") or "")),
                    generation_instruction_context=instruction_context,
                ))
            scripts = self._normalize_enhanced_scripts(scripts, node_ids)
            return {"scripts": scripts or fallback["scripts"], "used_fallback": True}

    def generate_single(self, node: dict[str, Any], course_name: str | None = None,
                        max_attempts: Optional[int] = None,
                        extra_instruction: str = "",
                        context_markdown: str = "",
                        teaching_plan: Optional[dict[str, Any]] = None,
                        generation_instruction_context: str = "") -> dict[str, Any]:
        """生成单个节点的讲稿（供 S4 修补时部分重生成使用）

        max_attempts: 收紧 LLM 重试次数（1 = 不重试），None 时按环境变量/默认值。
        extra_instruction: [B6] 局部重生成时的修改指令（如"精简内容，增加生活案例"），
                           追加到 user_prompt，不传则行为与原版完全一致。
        context_markdown: 检索到的参考材料（知识库证据）。非空时作为「参考材料」块
                          追加到 user_prompt，格式与 outline.py 的 _format_evidence 一致。
                          不传则 prompt 与之前逐字相同（向后兼容）。
        teaching_plan: 教学表达规划器对**这一页**的决策。非空时作为**约束**注入
                      （见 _plan_constraint），不传则 prompt 与之前逐字相同。
        """
        node_id = str(node.get("node_id") or "node_unknown")
        title = str(node.get("title") or "未命名节点")
        core_points = node.get("core_points") or []
        examples = node.get("examples") or []
        confusions = node.get("common_confusions") or []
        summary = str(node.get("summary") or "")

        fallback = self._single_fallback(node_id, title, summary, core_points, examples, confusions)
        try:
            system_prompt = (
                "你是高校课程智能讲授编排助手，负责为单个教学节点生成分段讲授脚本。\n"
                "【强制约束】\n"
                "1. 输出严格JSON，字段：node_id / title / script / segments（数组）/ point_details（数组）。\n"
                "2. segments 必填：segment_id（seg_001格式）/ text（≤500字符）/ node_id / segment_type / estimated_seconds（15-120整数）。\n"
                "3. segment_type 仅允许：opening | explanation | example | interaction | transition | summary。\n"
                "4. 每个节点生成 2-4 个 segments，首个为 opening，末个为 summary 或 transition。\n"
                "5. script = 所有 segments.text 拼接。\n"
                "6. point_details：每个要点一项 {point, detail}，共 3-5 项。point 是要点本身"
                "（≤30字），detail 是 1~2 句展开（≤80字）。这是幻灯片正文的主角 —— "
                "detail 要回答「所以呢」，不要把 point 换个说法复述一遍。\n"
                "7. 额外可选字段：interactive_questions / key_points / difficulty / layout_hint。\n"
                "8. 禁止编造 node_id，不得缺少任何必填字段。\n"
                "9. 输出严格遵循 JSON Schema，additionalProperties=False。"
            )
            user_prompt = (
                f"课程名: {course_name or '未提供'}\n"
                f"节点标题: {title}\n摘要: {summary}\n"
                f"核心要点: {json.dumps(core_points, ensure_ascii=False)}\n"
                f"示例: {json.dumps(examples, ensure_ascii=False)}\n"
                f"易错点: {json.dumps(confusions, ensure_ascii=False)}\n"
            )
            if teaching_plan:
                user_prompt += "\n" + _plan_constraint(teaching_plan)
            if generation_instruction_context:
                user_prompt += f"\n\n【本次统一生成指令】\n{generation_instruction_context}\n"
            if extra_instruction:
                user_prompt += f"\n【修改要求】\n{extra_instruction}\n"
            if context_markdown:
                user_prompt += (
                    "\n【参考材料】\n"
                    "以下是从知识库检索到的相关资料，生成讲稿时须以其为准，"
                    "不得编造材料中不存在的知识点：\n"
                    f"{context_markdown}\n"
                )
            result = self._get_llm(max_attempts).chat_json(system_prompt, user_prompt,
                                                           temperature=self.config.temperature)
            segments = _normalize_single_segments(result.get("segments"), node_id)
            script = self._clean_text(result.get("script"))
            if not script and segments:
                # prompt 约定 script = 所有 segments.text 拼接，模型漏给 script 时补齐，
                # 保证两者不会互相矛盾（与 _normalize_enhanced_scripts 同一处理）
                script = "".join(seg["text"] for seg in segments)
            return {
                "node_id": node_id, "title": title,
                "script": script or fallback["script"],
                # 不混用 fallback 的 segments：那会和模型给的 script 对不上，
                # 预览里「讲授文本」与「分段」各说各话比没有分段更糟。
                # 模型整批失败走下面的 except 分支，返回的 fallback 本身自洽。
                "segments": segments,
                "point_details": normalize_point_details(result.get("point_details")),
                "mindmap_markdown": self._clean_text(result.get("mindmap_markdown")) or fallback["mindmap_markdown"],
                "interactive_questions": result.get("interactive_questions") or fallback["interactive_questions"],
                "reteach_script": self._clean_text(result.get("reteach_script")) or fallback["reteach_script"],
                "transition": self._clean_text(result.get("transition")) or fallback["transition"],
            }
        except Exception:
            return fallback

    # ── 批量生成 ──

    def _run_batch_generation(self, markdown: str,
                              nodes: list[dict], course_name: str | None,
                              plans: Optional[dict[str, Any]] = None,
                              generation_instruction_context: str = "") -> list[dict]:
        system_prompt = (
            "你是课堂讲稿生成助手，负责为每个教学节点生成可直接讲授的脚本。\n"
            "【强制约束】\n"
            "1. 每个节点必须输出：node_id / title / script / segments，不得缺少任意字段。\n"
            "2. segments 是数组，每个元素须包含：segment_id（seg_001 格式）/ text（≤500字符）/ node_id（必须来自输入节点树）。\n"
            "3. 每个节点至少生成 2-4 个 segments：开场(seg_001) → 讲解 → 互动/案例 → 小结/过渡。\n"
            "4. script 字段为所有 segments.text 的拼接，用于兼容旧版渲染器。\n"
            "5. point_details：每个要点一项 {point, detail}，共 3-5 项。point 是要点本身"
            "（≤30字），detail 是 1~2 句展开（≤80字），回答「所以呢」，不要把 point 复述一遍。\n"
            "6. node_id 必须使用节点树中已存在的 node_id，禁止自创或编造。\n"
            "7. 输出严格遵循 JSON Schema，additionalProperties=False。"
        )
        user_prompt = (
            f"课程名: {course_name or '未命名课程'}\n"
            f"原始 Markdown:\n{markdown}\n\n"
            f"节点树:\n{json.dumps(nodes, ensure_ascii=False)}\n\n"
            "请输出 scripts 数组；每个元素包含 node_id/title/script/segments。"
        )
        brief = _plans_brief(plans, nodes)
        if brief:
            user_prompt = f"{user_prompt}\n\n{brief}"
        if generation_instruction_context:
            user_prompt += f"\n\n【本次统一生成指令】\n{generation_instruction_context}"
        result = self._get_llm().chat_with_schema(
            system_prompt, user_prompt,
            build_stage3_script_schema(),
            temperature=self.config.temperature,
        )
        node_ids = {n["node_id"] for n in nodes}
        return normalize_stage3_scripts(extract_list_payload(result, "scripts"), node_ids)

    def _run_enhanced_batch(self, markdown: str,
                            nodes: list[dict], course_name: str | None,
                            plans: Optional[dict[str, Any]] = None,
                            generation_instruction_context: str = "") -> list[dict]:
        system_prompt = (
            "你是课堂讲稿生成助手（增强版），负责为每个教学节点生成分段讲授脚本。\n"
            "【强制约束】\n"
            "1. 输出严格JSON，格式：{\"scripts\":[{\"node_id\":\"\",\"title\":\"\",\"script\":\"\",\"segments\":[...]}]}。\n"
            "2. segments 必填字段：segment_id（seg_001格式）/ text（≤500字符）/ node_id / segment_type / estimated_seconds（15-120整数）。\n"
            "3. segment_type 仅允许：opening | explanation | example | interaction | transition | summary。\n"
            "4. 可选字段：difficulty（easy/medium/hard）/ interaction_hint（具体教师话术）/ knowledge_card（{term,definition,formula,tags}）。\n"
            "5. 每个节点生成 2-4 个 segments：开场 opening(seg_001) → 讲解 explanation → 互动 interaction/案例 example → 小结 transition/summary。\n"
            "6. point_details：每个要点一项 {point, detail}，共 3-5 项。point 是要点本身"
            "（≤30字），detail 是 1~2 句展开（≤80字），回答「所以呢」，不要把 point 复述一遍。\n"
            "7. node_id 必须使用节点树中已存在的 node_id，禁止自创或编造。\n"
            "8. script = 所有 segments.text 拼接，用于兼容旧版渲染器。\n"
            "9. 输出严格遵循 JSON Schema，additionalProperties=False。"
        )
        user_prompt = (
            f"课程名: {course_name or '未命名课程'}\n原始MD:\n{markdown}\n\n"
            f"节点树:\n{json.dumps(nodes, ensure_ascii=False)}\n\n"
            "每个节点生成 2-4 个分段讲授 segments，node_id 必须来自节点树。"
        )
        brief = _plans_brief(plans, nodes)
        if brief:
            user_prompt = f"{user_prompt}\n\n{brief}"
        if generation_instruction_context:
            user_prompt += f"\n\n【本次统一生成指令】\n{generation_instruction_context}"
        result = self._get_llm().chat_with_schema(
            system_prompt, user_prompt,
            build_enhanced_script_schema(),
            temperature=self.config.temperature,
        )
        scripts = extract_list_payload(result, "scripts")
        valid_ids = {n["node_id"] for n in nodes}
        valid_list = sorted(valid_ids)
        for idx, script in enumerate(scripts):
            raw_id = str(script.get("node_id") or "").strip()
            if raw_id in valid_ids:
                continue
            mapped = valid_list[idx] if idx < len(valid_list) else (valid_list[-1] if valid_list else None)
            if mapped:
                script["node_id"] = mapped
                for seg in script.get("segments") or []:
                    # 元素非 dict（如 LLM 把 segments 输出成 str）时跳过，避免整批降级
                    if isinstance(seg, dict):
                        seg["node_id"] = mapped
        return scripts

    @staticmethod
    def _generation_instruction_context(instruction_set: Optional[dict[str, Any]]) -> str:
        if not isinstance(instruction_set, dict):
            return ""
        payload = {
            "output_requirements": instruction_set.get("output_requirements") or {},
            "presentation": instruction_set.get("presentation") or {},
            "generation_mode": instruction_set.get("generation_mode") or "",
        }
        payload = {key: value for key, value in payload.items() if value}
        return json.dumps(payload, ensure_ascii=False) if payload else ""

    # ── LLM 客户端 ──

    def _get_llm(self, max_attempts: Optional[int] = None) -> LLMClient:
        """获取 LLM 客户端（懒创建，支持注入）

        max_attempts 非空时返回收紧重试配置的新客户端（批量降级路径用，
        避免 N 节点 × (timeout+退避) 的最坏延迟放大），注入的 llm_client
        仅在未收紧时复用。
        """
        if max_attempts is None:
            if self._llm is not None:
                return self._llm
            return LLMClient(temperature=self.config.temperature, model=self.config.model or None)
        return LLMClient(temperature=self.config.temperature,
                         model=self.config.model or None, max_attempts=max_attempts)

    # ── 兜底 ──

    def _fallback_scripts(self, nodes: list[dict], course_name: str | None) -> dict[str, Any]:
        """LLM 不可用时的兜底讲稿"""
        scripts = []
        for idx, node in enumerate(nodes, start=1):
            nid = node["node_id"]
            title = node["title"]
            summary = node.get("summary") or title
            script_text = f"接下来讲解节点 {nid}: {title}。这段重点是: {summary}。请同学们先理解概念，再结合实际场景加以应用。"
            scripts.append({
                "node_id": nid, "title": title, "script": script_text,
                "segments": [{"segment_id": f"seg_{idx}_1", "text": script_text, "node_id": nid}],
            })
        return {"scripts": scripts}

    def _enhanced_fallback(self, nodes: list[dict], course_name: str | None) -> dict[str, Any]:
        fallback = self._fallback_scripts(nodes, course_name)
        scripts = []
        for idx, node in enumerate(nodes, start=1):
            nid = node["node_id"]
            title = node["title"]
            st = f"讲解节点 {nid}: {title}。"
            scripts.append({
                "node_id": nid, "title": title, "script": st,
                "segments": [{
                    "segment_id": f"seg_{idx}_1", "text": st, "node_id": nid,
                    "segment_type": "explanation", "estimated_seconds": 45,
                    "difficulty": "medium", "interaction_hint": f"提问: 你对{title}有什么理解?",
                    "knowledge_card": {"term": title, "definition": f"关于{title}的核心知识",
                                       "formula": "", "tags": ["core"]},
                }],
            })
        return {"scripts": scripts}

    def _single_fallback(self, node_id: str, title: str, summary: str,
                         core_points: list, examples: list, confusions: list) -> dict:
        details = "; ".join(core_points[:3]) if core_points else summary or title
        example_text = examples[0] if examples else f"可以结合{title}的典型应用场景帮助学生理解。"
        # 兜底讲稿与 segments 同源：script 严格等于各 segment.text 拼接，与生成 prompt
        # 的约定（"script = 所有 segments.text 拼接"）保持一致。此前只回 script 不回
        # segments，导致局部重生成路径（partial_content 按 segments 落库）每次都会把
        # 该节点的分段清空，预览里的「分段」区块随之消失。
        parts = [
            ("opening", f"这一部分我们围绕「{title}」来讲。", 30),
            ("explanation", f"先抓住几个关键点: {details}。", 60),
            ("example", f"讲到这里时，可以用「{example_text}」作为课堂例子。", 60),
            ("summary", "最后再回到本节点结论，帮助学生形成完整理解。", 30),
        ]
        segments = [
            {
                "segment_id": f"seg_{index:03d}", "text": text, "node_id": node_id,
                "segment_type": segment_type, "estimated_seconds": seconds,
            }
            for index, (segment_type, text, seconds) in enumerate(parts, start=1)
        ]
        return {
            "node_id": node_id, "title": title,
            # 与改动前的 script 逐字相同，只是改成由 segments 拼出，避免两处漂移
            "script": "".join(seg["text"] for seg in segments),
            "segments": segments,
            "mindmap_markdown": f"- {title}",
            "interactive_questions": [f"你觉得「{title}」最关键的点是什么？"],
            "reteach_script": f"重新解释{title}的核心概念。",
            "transition": f"理解完「{title}」之后，进入下一个知识节点。",
        }

    # ── 工具 ──

    @staticmethod
    def _clean_text(value: Any) -> str:
        return re.sub(r"\n{3,}", "\n\n", str(value or "").strip())

    @staticmethod
    def _normalize_enhanced_scripts(scripts: list, valid_node_ids: set) -> list:
        normalized = []
        for item in scripts or []:
            node_id = _resolve_script_node_id(item, valid_node_ids)
            if not node_id:
                continue
            raw_segments = (item or {}).get("segments")
            if not isinstance(raw_segments, list):
                # segments 被 LLM 输出成 str/dict 等非 list 类型时丢弃（M1-4B P2）：
                # 原实现直接迭代会触发 AttributeError，导致 generate_enhanced 整批降级
                raw_segments = []
            segments = []
            for seg in raw_segments:
                if not isinstance(seg, dict):
                    continue
                seg_id = str(seg.get("segment_id") or "").strip()
                text = str(seg.get("text") or "").strip()
                if not seg_id or not text:
                    continue
                segments.append({
                    "segment_id": seg_id, "text": text,
                    "node_id": _resolve_seg_node_id(seg, node_id, valid_node_ids),
                    "segment_type": str(seg.get("segment_type") or "explanation").strip(),
                    "estimated_seconds": _safe_estimated_seconds(seg.get("estimated_seconds")),
                    "difficulty": str(seg.get("difficulty") or "medium").strip(),
                    "interaction_hint": str(seg.get("interaction_hint") or "").strip(),
                    "knowledge_card": seg.get("knowledge_card") or {},
                })
            script_text = str((item or {}).get("script") or "").strip()
            if not script_text and segments:
                script_text = "".join(s["text"] for s in segments)
            raw_type = str((item or {}).get("type") or (item or {}).get("node_type") or "content").strip()
            core_pts = (item or {}).get("core_points") or []
            key_pts = (item or {}).get("key_points") or []
            questions_raw = (item or {}).get("questions")
            interactive_raw = (item or {}).get("interactive_questions")
            normalized.append({
                "node_id": node_id,
                "title": str((item or {}).get("title") or node_id).strip() or node_id,
                "script": script_text,
                # 补齐与 normalize_stage2_nodes（函数A）对齐的三个字段（M1-4B P3）
                "summary": str((item or {}).get("summary") or "").strip(),
                "source_span": str((item or {}).get("source_span") or "").strip(),
                "prerequisites": normalize_text_list((item or {}).get("prerequisites")),
                # 与函数A对齐的值映射：content → slide，其余白名单外值收敛为 slide
                "node_type": sanitize_node_type(raw_type),
                "type": sanitize_node_type(raw_type),
                # 类型归一：str/list[dict]/dict 等脏数据统一转为 list[str]（M1-4 P5）
                "key_points": normalize_text_list(key_pts) or normalize_text_list(core_pts),
                "core_points": normalize_text_list(core_pts),
                "questions": normalize_text_list(questions_raw) or normalize_text_list(interactive_raw),
                "interactive_questions": normalize_text_list(interactive_raw) or normalize_text_list(questions_raw),
                "segments": segments,
                # 内容页「要点展开」的正文来源。缺失时页面上少一块，不会变形。
                "point_details": normalize_point_details((item or {}).get("point_details")),
                "layout_hint": _normalize_optional_text((item or {}).get("layout_hint")),
                "font_size_hint": _normalize_optional_text((item or {}).get("font_size_hint")),
                "text_alignment": _normalize_optional_text((item or {}).get("text_alignment")),
                "slide_background": _normalize_optional_text((item or {}).get("slide_background")),
            })
        return normalized


def _resolve_script_node_id(item: dict, valid_node_ids: set) -> str:
    raw = str((item or {}).get("node_id") or "").strip()
    if not raw:
        arr = (item or {}).get("node_ids") or []
        if arr:
            raw = str(arr[0]).strip()
    if raw in valid_node_ids:
        return raw
    if valid_node_ids:
        return sorted(valid_node_ids)[0]
    return ""


def _resolve_seg_node_id(seg: dict, node_id: str, valid_node_ids: set) -> str:
    raw = str((seg or {}).get("node_id") or "").strip()
    if not raw:
        arr = (seg or {}).get("node_ids") or []
        if arr:
            raw = str(arr[0]).strip()
    if not raw or raw not in valid_node_ids:
        raw = node_id
    return raw
