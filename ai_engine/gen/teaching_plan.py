"""教学表达规划器 —— 「这个知识点应该怎么教」。

为什么要有这一层
----------------
此前的链路是 ``核心知识点 → PPT 模板``：写稿阶段拿到节点标题与要点，直接渲染成
页面。于是产出的东西更像"演讲稿提纲卡片"，而不是授课用的 PPT —— 缺的正是
「这个知识点，学生到底需要**看见什么**才能理解」这一步判断。

本模块把链路补成::

    教学意图 → 核心知识点 → 【判断怎么教】→ 表达形式 → 页面

它回答五个问题：

1. 这一页的教学目的是什么           → ``teaching_goal``
2. 学生最需要理解的是什么关系       → ``visual_type`` / ``visual_structure``
3. 最适合什么视觉表达               → 同上
4. PPT 上应该展示多少内容           → ``density``
5. 哪些留给教师口头讲               → ``teacher_note``

唯一决策点
----------
表达形式的决策**只在本模块发生一次**。下游全部是机械映射：

- :func:`plan_to_figure` 把 plan 翻成 ``page_spec`` 认识的 figure 描述（无 LLM 调用）
- 写稿阶段（``gen/node.py``）把 plan 当**约束**注入 prompt，不重新决策
- 预览与导出都从 ``page_spec`` 取内容，各自只负责"怎么画"

这条约束是「预览与导出不再分叉」的前提：如果导出侧再自己判断一次该画什么
（改造前 ``export_ppt._select_visualization`` 做的事），两个渲染器立刻各说各话。

不是每个知识点都要"发挥"
------------------------
用户明确提过：「不是每个核心知识点都要'发挥'。否则很容易变成 AI 自嗨，PPT 塞满
东西。」所以 ``visual_type`` **允许且鼓励**取 ``"none"``，并且这条约束有两道保险：

- prompt 给的是「什么时候**不**该出图」的判据，不只是「什么时候出什么图」
- :func:`apply_figure_quota` 在代码层强制配额：出图页数超过 ``MAX_FIGURE_PAGE_RATIO``
  时按结构性强弱截断，超出部分改判 ``none``

第二道是关键 —— 它不依赖模型自觉。只写 prompt 的话，模型迟早会给每一页都配一张图。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable, Optional

# page_spec 是「什么画得出来」的唯一权威，本模块把合法性判断整个交给它，不另立一套。
# 依赖是单向的（page_spec 不反向引用本模块），故模块级导入安全。
from .page_spec import (
    MAX_CONCLUSION_CHARS,
    MAX_FIGURE_ITEMS,
    extract_key_points,
    normalize_figure,
    resolve_kind,
    split_matrix_cells,
)

logger = logging.getLogger(__name__)

#: 规划输出的表达形式。``none`` = 这一页不出图（定义、纯记忆性知识、结构说不清时）。
VISUAL_TYPES = ("flow", "compare", "cycle", "hierarchy", "chart", "matrix", "none")

#: PPT 上展示多少。minimal = 只大字结论 + 图示；standard = 再加要点展开。
DENSITIES = ("minimal", "standard")

#: 出图页数占全课件页数的上限。超出部分强制改判 none —— 这道闸不依赖模型自觉。
MAX_FIGURE_PAGE_RATIO = 0.6

#: 流程/循环/层级类图示的最少标签数。少于 2 个构不成关系，"画"出来只是把一句话
#: 装进框里 —— 这正是该判 none 的典型。上限不由本模块管：标签数量、行列数、
#: 数值合法性统一交给 page_spec.normalize_figure 裁定，避免两处各校验一套慢慢漂移。
MIN_VISUAL_ITEMS = 2

#: 兜底启发式用的特征词（原先在 export_ppt 里，现降级为「没有 LLM 时」的确定性路径）
_FLOW_KEYWORDS = ("步骤", "流程", "首先", "然后", "接着", "其次", "最后",
                  "第一", "第二", "第三", "随后", "最终")
_FLOW_LEADING_RE = re.compile(
    r"^(首先|然后|接着|其次|最后|随后|最终|第[一二三四五六]步|步骤[一二三四五六]?)[，,：:、\s]*")
_COMPARE_KEYWORDS = ("对比", "相比", "区别", "差异", "不同之处", "优劣")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[%％]")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？；;.!?\n]")


# ---- 归一 ----

def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _label_text(value: Any) -> str:
    """标签取值：dict 元素取 text/label/value 字段。

    不能直接 ``str(dict)`` —— 那会把 ``{'text': '甲'}`` 原样当成标签画到幻灯片上。
    """
    if isinstance(value, dict):
        return _text(value.get("text") or value.get("label") or value.get("value"))
    return _text(value)


def _visual_item_count(payload: Any) -> int:
    """图示结构里有几"条"内容 —— 用于配额排序与最少标签数判断。"""
    if isinstance(payload, dict):
        if "columns" in payload or "rows" in payload:
            # matrix：行列都算内容，取较大者避免"1 列 4 行"被误判为只有 1 条
            return max(len(_as_list(payload.get("columns"))), len(_as_list(payload.get("rows"))))
        if "left" in payload or "right" in payload:
            sides = [payload.get("left"), payload.get("right")]
            return max((len(_as_list((s or {}).get("items"))) for s in sides), default=0)
        return 0
    if isinstance(payload, list):
        return len(payload)
    return 0


def _normalize_structure(visual_type: str, payload: Any) -> Any:
    """按 visual_type 把模型给的 visual_structure 收敛成约定形态。

    各形态（与 page_spec.normalize_figure 的输入契约一致）：

      flow/cycle/hierarchy  ["甲", "乙", "丙"]
      compare               {"left": {"title", "items"}, "right": {...}}
      matrix                {"columns": [...], "rows": [[...]]}
      chart                 [{"label": "冒泡", "value": 45}, ...]

    这一层只管**形态**（把模型的口语化输出掰成契约形状）；**合法性**（标签够不够、
    数值是不是数、行列对不对齐）一律交给 normalize_figure 裁定，见 normalize_plan。
    """
    if visual_type in ("flow", "cycle", "hierarchy"):
        items = [_label_text(x) for x in _as_list(payload)]
        items = [x for x in items if x]
        # 少于两条的"关系图"是自欺 —— 一个框装一句话不叫图示
        return items if len(items) >= MIN_VISUAL_ITEMS else None

    if visual_type == "compare":
        raw = payload if isinstance(payload, dict) else {}
        sides: dict[str, Any] = {}
        for key in ("left", "right"):
            side = raw.get(key)
            if not isinstance(side, dict):
                side = {"title": _text(side), "items": []}
            items = [_label_text(x) for x in _as_list(side.get("items"))]
            sides[key] = {"title": _text(side.get("title")), "items": [x for x in items if x]}
        # 两边都空等于没画；只有一边有内容仍然成立（"新方案 vs 现状"常一边为空标题）
        return sides if any(s["items"] for s in sides.values()) else None

    if visual_type == "matrix":
        raw = payload if isinstance(payload, dict) else {}
        # 列与行的切分口径与 page_spec 共用 —— 模型常把一行写成 "甲、乙、丙"
        columns = [c for c in split_matrix_cells(raw.get("columns")) if c]
        if not columns:
            return None
        rows: list[list[str]] = []
        for row in _as_list(raw.get("rows")):
            cells = split_matrix_cells(row)
            if not any(cells):
                continue
            # 模型经常给不齐列数：按 columns 长度补齐/截断，缺格留空
            rows.append((cells + [""] * len(columns))[:len(columns)])
        return {"columns": columns, "rows": rows} if rows else None

    if visual_type == "chart":
        series: list[dict[str, Any]] = []
        for entry in _as_list(payload):
            if not isinstance(entry, dict):
                continue
            label = _text(entry.get("label") or entry.get("name"))
            if label:
                # 数值合法性交给 page_spec 裁定（连 "45%" 这种带装饰的串它都会清洗），
                # 这里只管形状 —— 两处各定一套"什么算合法数值"必然慢慢漂移
                series.append({"label": label, "value": entry.get("value")})
        # 只有一根柱子谈不上"关系"，改判 none
        return series if len(series) >= 2 else None

    return None


def _to_figure(visual_type: str, structure: Any, title: str) -> dict[str, Any] | None:
    """(表达形式, 结构, 标题) → page_spec 认得的 figure 描述。纯拼装，不做判断。"""
    if visual_type == "compare":
        if not isinstance(structure, dict):
            return None
        return {"kind": "compare", "title": title,
                "left": structure.get("left") or {}, "right": structure.get("right") or {}}
    if visual_type == "matrix":
        if not isinstance(structure, dict):
            return None
        return {"kind": "matrix", "title": title,
                "columns": structure.get("columns") or [], "rows": structure.get("rows") or []}
    if visual_type == "chart":
        return {"kind": "chart", "title": title, "series": _as_list(structure)}
    if visual_type in ("flow", "cycle", "hierarchy"):
        return {"kind": visual_type, "title": title, "items": _as_list(structure)}
    return None


def _structure_of(figure: dict[str, Any]) -> Any:
    """规范化后的 figure → plan 里的 visual_structure（_to_figure 的逆）。

    存回去的是**规范化之后**的形态，于是 plan 里记的就是将来真会画出来的东西 ——
    "打印 plans 逐条核对"时看到的不是模型的原始意愿，而是实际结果。
    """
    kind = figure["kind"]
    if kind == "compare":
        return {"left": figure["left"], "right": figure["right"]}
    if kind == "matrix":
        return {"columns": figure["columns"], "rows": figure["rows"]}
    if kind == "chart":
        return figure["series"]
    return figure["items"]


def normalize_plan(raw: Any, node_id: str = "") -> dict[str, Any] | None:
    """模型输出的一条规划 → 规范化 dict；不可用时返回 None。

    脏数据一律降级为「这页没有规划」，绝不抛异常 —— 规划失败不该拖垮整份课件。

    合法性不在这里另写一套：把候选 figure 交给 ``page_spec.normalize_figure``
    裁定（它是"什么画得出来"的唯一权威）。裁决为不可画就如实记成 ``none``，
    而不是留着 ``visual_type`` 说一套、下游按另一套渲染。
    """
    if not isinstance(raw, dict):
        return None

    visual_type = _text(raw.get("visual_type")).lower()
    if visual_type not in VISUAL_TYPES:
        visual_type = "none"

    conclusion = _text(raw.get("key_conclusion"))
    knowledge_point = _text(raw.get("knowledge_point"))

    structure: Any = None
    if visual_type != "none":
        coerced = _normalize_structure(visual_type, raw.get("visual_structure"))
        figure = _to_figure(visual_type, coerced, conclusion or knowledge_point)
        normalized = normalize_figure({"figure": figure}) if figure else None
        if normalized is None:
            visual_type = "none"
        else:
            structure = _structure_of(normalized)

    density = _text(raw.get("density")).lower()
    plan = {
        "node_id": _text(raw.get("node_id")) or node_id,
        "knowledge_point": knowledge_point,
        "teaching_goal": _text(raw.get("teaching_goal")),
        "key_conclusion": conclusion,
        "visual_type": visual_type,
        "visual_structure": structure,
        "teacher_note": _text(raw.get("teacher_note")),
        "density": density if density in DENSITIES else "standard",
    }
    # 一条有效信息都没有的规划等于没有规划
    if not any(plan[k] for k in ("teaching_goal", "key_conclusion", "teacher_note")) \
            and visual_type == "none":
        return None
    return plan


# ---- plan → figure（机械映射，无第二次决策）----

def plan_to_figure(plan: Any) -> dict[str, Any] | None:
    """把规划里的表达形式翻成 ``page_spec.normalize_figure`` 认得的 figure 描述。

    这里**不做任何判断** —— 画什么、画几张，规划阶段已经定死了。合法性已在
    normalize_plan 里由 normalize_figure 裁定过，此处只是搬运。
    """
    if not isinstance(plan, dict):
        return None
    kind = _text(plan.get("visual_type")).lower()
    if kind in ("", "none"):
        return None
    title = _text(plan.get("key_conclusion")) or _text(plan.get("knowledge_point"))
    return _to_figure(kind, plan.get("visual_structure"), title)


# ---- 配额：不依赖模型自觉的那道闸 ----

#: 排序用的结构性强弱。越靠前越值得配图；none 永远排最后。
_STRUCTURE_RANK = {"flow": 0, "matrix": 1, "chart": 2, "compare": 3, "cycle": 4, "hierarchy": 5}


def _structure_score(plan: dict[str, Any]) -> tuple[int, int]:
    """(结构性强弱, 内容条数)。越小越该保留。"""
    return (
        _STRUCTURE_RANK.get(_text(plan.get("visual_type")).lower(), 99),
        -_visual_item_count(plan.get("visual_structure")),
    )


def apply_figure_quota(
    plans: dict[str, dict[str, Any]],
    ratio: float = MAX_FIGURE_PAGE_RATIO,
    *,
    content_ids: Optional[set[str]] = None,
) -> dict[str, dict[str, Any]]:
    """限制出图页数占比，超出部分改判 ``none``。

    「不是每个知识点都要发挥」这条要求的硬约束。模型迟早会给每一页都配上图，
    只靠 prompt 拦不住 —— 这里按结构性强弱排序后截断，返回**新的 dict**，
    不修改入参。

    ``content_ids`` 给了就只按**内容页**数量算配额：封面 / 目录 / 测验 / 小结的
    表达形式已由页型定死、本就不该出图，把它们算进分母等于凭空放宽配额
    （10 页里 4 页是结构性页时，按全页数算允许 6 张图 = 内容页可以全部出图）。
    """
    result = {node_id: dict(plan) for node_id, plan in plans.items()}
    drawable = [
        (node_id, plan) for node_id, plan in result.items()
        if _text(plan.get("visual_type")).lower() not in ("", "none")
    ]
    if not drawable:
        return result

    base = len(result)
    if content_ids is not None:
        base = sum(1 for node_id in result if node_id in content_ids)
    allowed = max(1, int(base * ratio))
    if len(drawable) <= allowed:
        return result

    keep = {node_id for node_id, _ in sorted(drawable, key=lambda kv: _structure_score(kv[1]))[:allowed]}
    for node_id, plan in result.items():
        if _text(plan.get("visual_type")).lower() not in ("", "none") and node_id not in keep:
            plan["visual_type"] = "none"
            plan["visual_structure"] = None
    return result


# ---- 兜底：没有 LLM 时的确定性规划 ----

def _node_text(node: dict[str, Any]) -> str:
    parts = []
    for field in ("content", "summary"):
        value = node.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def _node_points(node: dict[str, Any]) -> list[str]:
    return extract_key_points(node)


def _heuristic_flow(node: dict[str, Any]) -> list[str]:
    """正文含顺序词时抽 2~4 步。原 export_ppt._detect_flow_steps 的逻辑。

    切分要一层层退：真实生成里正文常常是**一整句**（"首先…，然后…，最后…"）而不是
    分行列表，只按句号切会得到一条、判不出流程。故按 行 → 句 → 逗号 依次尝试，
    哪一层能切出 ≥2 条带顺序词的片段就用哪一层；一层都不行就如实返回空
    （宁可判 none，也不硬凑一张"流程"）。
    """
    text = _node_text(node)
    if not text or not any(k in text for k in _FLOW_KEYWORDS):
        return []
    for pattern in (r"\n+", _SENTENCE_SPLIT_RE, r"[，,]\s*"):
        parts = [p.strip() for p in re.split(pattern, text) if p.strip()]
        if len(parts) < 2:
            continue
        steps = [_FLOW_LEADING_RE.sub("", p).strip() for p in parts if any(k in p for k in _FLOW_KEYWORDS)]
        # 不截断标签：它进 foreignObject 由浏览器换行，硬切会把语义词切碎
        steps = [s for s in steps if s]
        if len(steps) >= 2:
            return steps[:4]
    return []


def _heuristic_chart(node: dict[str, Any]) -> list[dict[str, Any]]:
    """正文/要点含 ≥2 个百分比时抽 (标签, 数值)。原 export_ppt._detect_comparison_bars。"""
    text = _node_text(node)
    # 要点常与正文同源（都是 extract_key_points 从正文拆出来的），直接拼上去会把
    # 同一个百分比数两遍，条形图凭空多出一倍。
    extra = [p for p in _node_points(node) if p and p not in text]
    if extra:
        text = "\n".join([text, *extra])
    if not text:
        return []

    series: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for match in _PERCENT_RE.finditer(text):
        context = text[max(0, match.start() - 12):match.start()]
        context = re.sub(r"^[\s，,。；;：:、()（）\-—*•]*", "", context)[-8:].strip()
        value = float(match.group(1))
        label = context or "占比"
        if (label, value) in seen:
            continue
        seen.add((label, value))
        series.append({"label": label, "value": value})
        if len(series) >= MAX_FIGURE_ITEMS:
            break
    if len(series) < 2 or all(s["value"] <= 0 for s in series):
        return []
    return series


def _heuristic_compare(node: dict[str, Any]) -> dict[str, Any] | None:
    """正文出现对比特征词且要点成对时，左右各取一半要点。"""
    points = _node_points(node)
    text = _node_text(node)
    if len(points) < 2 or not any(k in text for k in _COMPARE_KEYWORDS):
        return None
    half = max(1, len(points) // 2)
    return {
        "left": {"title": "", "items": points[:half]},
        "right": {"title": "", "items": points[half:]},
    }


def heuristic_plan(node: dict[str, Any]) -> dict[str, Any]:
    """没有 LLM（``AI_GEN_MODE=mock``）或规划调用失败时的确定性规划。

    这里承载的是原先 ``export_ppt._select_visualization`` 的启发式 —— 它没有被删除，
    而是从"导出侧的独立决策"降级为"规划器的兜底路径"。差别在于：现在它只是规划器
    众多实现中的一种，输出仍要经过配额与归一，下游拿到的形态完全一致。
    """
    points = _node_points(node)
    summary = _text(node.get("summary")) or _text(node.get("content"))
    # 按句切分时**句末标点会一并去掉**（re.split 不带捕获组就丢弃分隔符）。这是想要
    # 的效果：大字结论是幻灯片上的一句断言，不是段落，末尾挂个句号只是排版噪音。
    first_sentence = next(
        (s.strip() for s in _SENTENCE_SPLIT_RE.split(summary) if s.strip()), ""
    )
    # 结论要能在幻灯片上大字显示：只取够短的那句，否则退回第一条要点，再不行留空。
    # 长度上限取自 page_spec（它才是"什么值得显示"的权威）——这里若另写一个数，
    # plan 会承诺一句最终渲染不出来的话。
    #
    # 节点自带 key_conclusion 时优先沿用它：那是更上游（小结页 / 上一轮落盘）已经写好
    # 的那句话，拿 summary 的首句去覆盖它没有道理。旧实现漏了这一步，于是「有结论、
    # 没 summary」的页在 plan 表和幻灯片上都变成空白。
    explicit = node.get("key_conclusion")
    conclusion = explicit.strip() if isinstance(explicit, str) else ""
    if not 0 < len(conclusion) <= MAX_CONCLUSION_CHARS:
        conclusion = next(
            (s for s in (first_sentence, points[0] if points else "")
             if 0 < len(s) <= MAX_CONCLUSION_CHARS),
            "",
        )

    visual_type, structure = "none", None
    # 封面 / 目录 / 测验 / 小结不出图：它们的表达形式已由页型定死，再配图是重复排版
    if resolve_kind(node) == "content":
        flow = _heuristic_flow(node)
        chart = _heuristic_chart(node)
        compare = _heuristic_compare(node)
        if flow:
            visual_type, structure = "flow", flow
        elif chart:
            visual_type, structure = "chart", chart
        elif compare:
            visual_type, structure = "compare", compare
        # 其余情况一律 none：单一要点构不成关系，两条以上散点也说不出关系。
        # 这不是"兜底失败"，正是「不是每个知识点都要发挥」那条要求的默认行为。

    return normalize_plan({
        "node_id": _text(node.get("node_id")),
        "knowledge_point": _text(node.get("title")),
        "teaching_goal": first_sentence,
        "key_conclusion": conclusion,
        "visual_type": visual_type,
        "visual_structure": structure,
        "teacher_note": "",
        "density": "standard",
    }, _text(node.get("node_id"))) or _empty_plan(node)


def _empty_plan(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": _text(node.get("node_id")),
        "knowledge_point": _text(node.get("title")),
        "teaching_goal": "",
        "key_conclusion": "",
        "visual_type": "none",
        "visual_structure": None,
        "teacher_note": "",
        "density": "standard",
    }


# ---- LLM 路径 ----

#: 规划器系统提示词。要点有两处与别处不同：
#:   1. 明确给出「什么时候**不**该出图」的判据 —— 只给"什么时候出什么图"必然导致每页都配图
#:   2. 话术与仓库根 `ppt设计哲学参考.md` 呼应（总-分-总、低位信息留给教师），不另起一套
PLAN_SYSTEM_PROMPT = (
    "你是高校课程的教学设计助手。给定一份课件的教学意图与各页知识点，"
    "你要逐页判断「这个知识点应该怎么教」，再据此决定这一页给学生看什么。\n"
    "【核心判据】先问自己：这个知识点，学生到底需要**看见什么**才能理解？\n"
    "把这个问题的答案落到 visual_type 上；答不上来就填 none。\n"
    "【什么时候不该出图 —— 这一条比出图更重要】\n"
    "1. 知识点是记忆性的（定义、术语、事实、年代）→ none。图只会是文字换个排列。\n"
    "2. 画出来的图与要点展开说的是同一件事 → none。图不是排版的重复。\n"
    "3. 说不清元素之间的关系，或标签少于 2 个、多于 5 个 → none。\n"
    "4. 一页最多一张图。宁可少画，不可硬凑 —— 塞满的 PPT 比朴素的更难懂。\n"
    "【visual_type 取值与适用】\n"
    "  flow      步骤、流程、因果、递进（元素之间是先后顺序）\n"
    "  compare   两方对比，或抽象概念的类比（A 之于 B 如同 C 之于 D）\n"
    "  matrix    三方及以上、或多维度的对比（行 × 列）\n"
    "  hierarchy 分类、原理结构（一个上位概念拆成若干下位）\n"
    "  cycle     循环、反馈（首尾相接）\n"
    "  chart     数值关系（出现百分比、倍数、量级对比）\n"
    "  none      见上四条判据\n"
    "【visual_structure 的形态须与 visual_type 对应】\n"
    "  flow / cycle / hierarchy : [\"标签1\", \"标签2\"]\n"
    "  compare                  : {\"left\": {\"title\": \"\", \"items\": []}, "
    "\"right\": {\"title\": \"\", \"items\": []}}\n"
    "  matrix                   : {\"columns\": [\"列1\"], \"rows\": [[\"格1\"]]}\n"
    "  chart                    : [{\"label\": \"名称\", \"value\": 45}]\n"
    "  none                     : null\n"
    "【其余字段】\n"
    "  teaching_goal   一句话：这一页要让学生理解什么\n"
    "  key_conclusion  一句话结论，将作为大字展示在幻灯片上（none 页尤其重要）\n"
    "  teacher_note    留给教师口头补充的内容 —— 写在这里的不会出现在幻灯片上，"
    "适合放案例、过渡语、提问、学生容易卡住的地方\n"
    "  density         minimal（只大字结论 + 图示）/ standard（再加要点展开）\n"
    "【强制约束】\n"
    "1. 输出严格 JSON，形如 {\"plans\": [ {...}, {...} ]}，plans 长度与给定节点数一致。\n"
    "2. 每项必含 node_id，且必须是给定节点之一，禁止编造。\n"
    "3. 按给定的节点顺序输出，不得遗漏任何一页。"
)


def _intent_brief(intent: Any) -> str:
    """教学意图 → 提示词里的一段摘要。intent 缺失是合法输入，返回空串即可。

    两个调用点传进来的东西不一样：``/gen/content`` 给的是 dict，而老师端真正走的
    ``/api/v1/gen/create`` 给的是 pydantic ``IntentSummary``。只认 dict 的话，后者会被
    静默判成「没有意图」—— 教学意图一路透传到规划器门口，却在这里被丢掉，规划退化成
    只看节点。这里统一兜住两种形态。
    """
    if hasattr(intent, "model_dump"):          # pydantic BaseModel（IntentSummary）
        data = intent.model_dump()
    else:
        data = intent if isinstance(intent, dict) else {}
    if not data:
        return ""

    def _join(value: Any) -> str:
        if isinstance(value, (list, tuple)):
            return "、".join(str(v).strip() for v in value if str(v).strip())
        return _text(value)

    rows = [
        ("教学主题", _text(data.get("topic"))),
        ("授课对象", _text(data.get("target_student"))),
        ("教学风格", _text(data.get("style"))),
        ("重点难点", _join(data.get("key_difficulties"))),
        ("预期成果", _join(data.get("expected_outcomes"))),
    ]
    body = "\n".join(f"- {label}：{value}" for label, value in rows if value)
    if not body:
        return ""
    return (
        "【教学意图】以下是教师在本课开始时确定的教学意图，"
        "规划表达形式时必须服从它（例如「案例驱动」的课应多给具体情境，"
        "「理论为主」的课应重在结构关系）：\n" + body
    )


def _nodes_brief(nodes: Iterable[dict[str, Any]]) -> str:
    rows = []
    for i, node in enumerate(nodes, start=1):
        rows.append({
            "index": i,
            "node_id": _text(node.get("node_id")),
            "title": _text(node.get("title")),
            "node_type": _text(node.get("node_type") or node.get("type")) or "content",
            "summary": _text(node.get("summary")),
            "key_points": _node_points(node),
        })
    return json.dumps(rows, ensure_ascii=False, indent=2)


def _extract_plans(result: Any) -> list[Any]:
    """从模型返回里取出 plans 数组；模型偶尔直接给数组或换名字，一并兼容。"""
    if isinstance(result, list):
        return result
    if not isinstance(result, dict):
        return []
    for key in ("plans", "pages", "items", "data"):
        value = result.get(key)
        if isinstance(value, list):
            return value
    return []


def _use_llm(llm: Optional[Any]) -> Optional[Any]:
    """取 LLM 客户端；mock 模式返回 None，直接走确定性兜底。"""
    if llm is not None:
        return llm
    from ..core.config import settings

    if getattr(settings, "is_mock", False):
        return None
    from ..core.llm import LLMClient

    return LLMClient()


def plan_deck(
    intent: Any,
    nodes: list[dict[str, Any]],
    *,
    evidence: str = "",
    llm: Optional[Any] = None,
) -> dict[str, dict[str, Any]]:
    """一次规划整份课件：``{node_id: plan}``。

    批量而非逐节点，是为了让模型能看到全局 —— 「这一页该不该出图」在整份课件的
    节奏里才判断得准（连着三页都是流程图，第四页就该换一种表达）。

    任何失败（无 LLM / 调用异常 / 返回不可用）都退回 :func:`heuristic_plan`，
    保证调用方永远拿得到一份完整的 ``{node_id: plan}``。
    """
    nodes = [n for n in nodes if isinstance(n, dict)]
    if not nodes:
        return {}
    by_id = {_text(n.get("node_id")): n for n in nodes}

    client = _use_llm(llm)
    plans: dict[str, dict[str, Any]] = {}
    if client is not None:
        try:
            user_prompt = _nodes_brief(nodes)
            brief = _intent_brief(intent)
            if brief:
                user_prompt = f"{brief}\n\n{user_prompt}"
            if evidence.strip():
                user_prompt += (
                    "\n\n【参考材料】\n"
                    "以下是从知识库检索到的资料，规划时须以其为准，"
                    "不得编造材料中不存在的知识点：\n"
                    f"{evidence.strip()}\n"
                )
            result = client.chat_json(PLAN_SYSTEM_PROMPT, user_prompt, temperature=0.2)
            for raw in _extract_plans(result):
                node_id = _text(raw.get("node_id")) if isinstance(raw, dict) else ""
                if node_id not in by_id:
                    continue  # 编造的 node_id 直接丢弃
                plan = normalize_plan(raw, node_id)
                if plan:
                    plans[node_id] = plan
        except Exception as exc:  # noqa: BLE001 —— 规划失败不该拖垮整份课件
            logger.warning("[TeachingPlan] 规划调用失败，退回启发式：%s", exc)
            plans = {}

    # 模型漏掉的页（或整批失败）逐页兜底 —— 宁可朴素，不能缺页
    for node_id, node in by_id.items():
        plans.setdefault(node_id, heuristic_plan(node))
    return apply_figure_quota(
        plans,
        content_ids={nid for nid, node in by_id.items() if resolve_kind(node) == "content"},
    )


def plan_node(
    intent: Any,
    node: dict[str, Any],
    *,
    evidence: str = "",
    llm: Optional[Any] = None,
) -> dict[str, Any]:
    """只规划一页（局部修改路径）。

    单页单独规划时看不到全局节奏，所以不套用配额 —— 配额是"整份课件的节奏"层面的
    约束，改一页时按它截断会把教师明确要求的那张图砍掉。
    """
    node = node if isinstance(node, dict) else {}
    node_id = _text(node.get("node_id"))
    client = _use_llm(llm)
    if client is not None:
        try:
            user_prompt = _nodes_brief([node])
            brief = _intent_brief(intent)
            if brief:
                user_prompt = f"{brief}\n\n{user_prompt}"
            if evidence.strip():
                user_prompt += f"\n\n【参考材料】\n{evidence.strip()}\n"
            result = client.chat_json(PLAN_SYSTEM_PROMPT, user_prompt, temperature=0.2)
            candidates = _extract_plans(result)
            if candidates:
                plan = normalize_plan(candidates[0], node_id)
                if plan:
                    return plan
        except Exception as exc:  # noqa: BLE001
            logger.warning("[TeachingPlan] 单页规划失败，退回启发式：%s", exc)
    return heuristic_plan(node)


# ---- 人工审阅 ----
#
# 「这个知识点，学生到底需要看见什么」是**主观判断**，不能只靠单测。规划结果必须
# 能被人一眼过一遍，尤其是"有没有不该出图的页被塞了图"。

def _char_width(char: str) -> int:
    """单字符占几列：中日韩等全角字符占 2 列，其余 1 列。"""
    return 2 if ord(char) > 0x2E80 else 1


def _display_width(text: Any) -> int:
    return sum(_char_width(char) for char in str(text))


def _clip(text: str, width: int) -> str:
    """按显示宽度截断，末尾补省略号（中文按两列算，否则表格会参差不齐）。"""
    if _display_width(text) <= width:
        return text
    out, used = "", 0
    for char in text:
        if used + _char_width(char) > width - 1:
            return out + "…"
        out, used = out + char, used + _char_width(char)
    return out


def _pad(text: str, width: int) -> str:
    text = _clip(text, width)
    return text + " " * max(0, width - _display_width(text))


def _structure_brief(structure: Any) -> str:
    """图示结构 → 一行摘要。"""
    if not structure:
        return "—"
    if isinstance(structure, dict):
        if "columns" in structure or "rows" in structure:
            head = "、".join(str(c) for c in structure.get("columns") or [])
            return f"[{head}] × {len(structure.get('rows') or [])}行"
        left, right = structure.get("left") or {}, structure.get("right") or {}
        return (f"{left.get('title') or '左'}({'、'.join(left.get('items') or [])}) "
                f"vs {right.get('title') or '右'}({'、'.join(right.get('items') or [])})")
    if isinstance(structure[0], dict):
        return "、".join(f"{s.get('label')}={s.get('value')}" for s in structure)
    return " → ".join(str(s) for s in structure)


def format_plan_table(plans: dict[str, dict[str, Any]]) -> str:
    """plans → 可人工审阅的表格。

    末行给出出图比例 —— 验收时要盯的正是"有没有不该出图的页被塞了图"。
    """
    widths = (10, 16, 10, 46, 30, 24)
    header = ("node_id", "知识点", "表达形式", "图示结构", "大字结论", "留给教师")
    sep = "-" * (sum(widths) + 3 * (len(widths) - 1))
    lines = [" | ".join(_pad(h, w) for h, w in zip(header, widths)), sep]

    for node_id, plan in plans.items():
        lines.append(" | ".join(_pad(cell, w) for cell, w in zip((
            node_id,
            plan.get("knowledge_point") or "",
            plan.get("visual_type") or "none",
            _structure_brief(plan.get("visual_structure")),
            plan.get("key_conclusion") or "",
            plan.get("teacher_note") or "",
        ), widths)))

    drawing = sum(1 for p in plans.values() if _text(p.get("visual_type")).lower() not in ("", "none"))
    lines.append(sep)
    lines.append(
        f"共 {len(plans)} 页，出图 {drawing} 页"
        f"（配额上限 {int(MAX_FIGURE_PAGE_RATIO * 100)}%）"
        f" —— 出图比例偏高时，逐条问：这一页学生真的需要**看见**什么吗？"
    )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    """命令行入口：对一批节点做表达规划并打印表格。

        python -m ai_engine.gen.teaching_plan nodes.json
        python -m ai_engine.gen.teaching_plan < nodes.json

    输入是节点数组，或含 ``nodes`` / ``intent`` 字段的对象（后者用得上教学意图）。
    """
    import argparse
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="教学表达规划：打印可审阅的 plan 表")
    parser.add_argument("nodes", nargs="?", help="节点 JSON 路径；省略则读 stdin")
    args = parser.parse_args(argv)

    raw = Path(args.nodes).read_text(encoding="utf-8") if args.nodes else sys.stdin.read()
    data = json.loads(raw)
    intent = data.get("intent") if isinstance(data, dict) else None
    nodes = (data.get("nodes") if isinstance(data, dict) else data) or []
    evidence = (data.get("evidence") or "") if isinstance(data, dict) else ""

    plans = plan_deck(intent, nodes, evidence=evidence)
    print(format_plan_table(plans))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
