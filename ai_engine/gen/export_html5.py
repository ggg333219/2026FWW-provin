"""
HTML5 互动小游戏导出模块 — S3/S4 课件生成（A12 赛题 4c/5c）

职责：
  interactive.py 产出的互动素材（quiz / flashcard）→ 单文件自包含 HTML5 小游戏

流程：
  节点数组 → extract_interactive_items（离线，不调 LLM）
          → render_interactive_html（内联 CSS+JS，零外部依赖，双击即可玩）
          → MinIO / 本地 / PPT 集成

两种游戏模式：
  - quiz      → 「答题挑战」：逐题作答、选项点击高亮、即时判分（对/错反馈动画）、
                答完显示总分与正确率、可重新开始
  - flashcard → 「知识翻卡」：卡片点击翻转（CSS 3D flip）、上一张/下一张、
                支持"我记住了/再看看"标记统计

设计约束：
  - 单文件自包含：所有 CSS/JS 内联，无任何 http(s) 外链或本地 src 引用
  - 移动端可用：viewport 自适应，触摸/点击均可操作
  - 教学风格：深蓝标题 + 微软雅黑（与 PPT/DOC 导出配色一致）
  - 内容安全：所有文本 html.escape，JSON 数据转义 </ 防止 </script> 逃逸
  - 离线：数据抽取纯规则化，不调用 LLM
"""

import json
import logging
import re
import unicodedata
from html import escape
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "render_interactive_html",
    "extract_interactive_items",
    "export_interactive_html",
    "extract_front_back",
    "ExportHTML5Config",
]


# ---------------------------------------------------------------------------
# 数据抽取（节点数组 → 互动素材，纯规则、无 LLM）
# ---------------------------------------------------------------------------

def _normalize_quiz_answer(answer: Any, options: list[str]) -> Optional[int]:
    """把 LLM 常见的答案形态归一化为选项下标。

    支持："A"/"B"/"a"（含全角后缀清洗，如 "C．"、"答案：B"）、0/1 整数下标、
    与选项文本完全一致的字符串。
    教学产品语义：无法识别时不强标正确答案（返回 None，前端只高亮选择不判对错），
    避免"选项 A 被错标为正确答案"；无法识别时记 warning 便于上游排查。
    """
    if isinstance(answer, bool) or answer is None:
        return None
    if isinstance(answer, dict):
        answer = next(
            (answer.get(key) for key in ("answer", "correct_answer", "option", "value")
             if answer.get(key) is not None),
            None,
        )
    if isinstance(answer, (list, tuple)):
        answer = answer[0] if len(answer) == 1 else None
    if answer is None:
        return None
    if isinstance(answer, int):
        return answer if 0 <= answer < len(options) else None
    if isinstance(answer, float) and answer.is_integer():
        idx = int(answer)
        return idx if 0 <= idx < len(options) else None
    text = unicodedata.normalize("NFKC", str(answer)).strip()
    # 清洗常见前后缀噪声：全角句点/顿号/逗号、"答案："前缀
    text = text.strip("．.、,，:： 　")
    text = re.sub(r"^(?:正确\s*)?(?:答案|选项)(?:\s*(?:是|为))?\s*[:：]?\s*", "", text)
    if not text:
        return None
    # 兼容 “B”、“B.”、“B. 选项正文”、“(B)” 等模型常见输出。
    letter_match = re.match(r"^[\(（]?\s*([A-Ha-h])(?:\s*[\)）.．、:：]|\s|$)", text)
    if letter_match:
        idx = "ABCDEFGH".index(letter_match.group(1).upper())
        return idx if idx < len(options) else None
    if text.isdigit():
        idx = int(text)
        return idx if 0 <= idx < len(options) else None
    for i, opt in enumerate(options):
        option_text = unicodedata.normalize("NFKC", str(opt)).strip()
        if option_text == text:
            return i
    logger.warning("[export_html5] quiz answer 无法识别，不强标正确答案: %r", answer)
    return None


def _normalize_question(q: Any) -> dict[str, Any] | None:
    """归一化单道题目：dict 形态（question/options/answer）→ 标准结构。

    纯文本题目（str）返回 None — 无选项/答案，不能判分，由调用方转为闪卡。
    """
    if not isinstance(q, dict):
        return None
    question = str(q.get("question") or q.get("title") or "").strip()
    options = [str(o) for o in (q.get("options") or []) if str(o).strip()]
    if not question or len(options) < 2:
        return None
    return {
        "question": question,
        "options": options,
        "answer": _normalize_quiz_answer(q.get("answer"), options),
        "explanation": str(q.get("explanation") or "").strip(),
    }


def extract_front_back(content: Any) -> tuple[str, str] | None:
    """Parse explicit front/back labels from authored interactive content."""
    text = str(content or "")
    front = re.search(r"正面\s*[:：]\s*(.*?)(?=\s*背面\s*[:：]|$)", text, re.S)
    back = re.search(r"背面\s*[:：]\s*(.*?)(?=\s*正面\s*[:：]|$)", text, re.S)
    front_text = front.group(1).strip() if front else ""
    front_text = re.sub(r"\s*点击卡片翻面查看答案[。.]?\s*", "", front_text).strip()
    back_text = back.group(1).strip() if back else ""
    return (front_text, back_text) if front_text or back_text else None


def _node_to_items(node: dict[str, Any]) -> list[dict[str, Any]]:
    """从单个节点抽取互动物料（quiz dict 题 + knowledge_card 闪卡 + 文本题转闪卡）。"""
    items: list[dict[str, Any]] = []

    # 1) 直接内嵌的互动物料（build_all 产物或历史快照）
    embedded = node.get("interactive_items") or (node.get("metadata") or {}).get("interactive")
    if isinstance(embedded, list):
        for raw in embedded:
            if not isinstance(raw, dict):
                continue
            t = str(raw.get("type") or "").lower()
            if t == "quiz":
                questions = [_normalize_question(q) for q in raw.get("questions") or []]
                questions = [q for q in questions if q]
                if questions:
                    items.append({"type": "quiz", "title": str(raw.get("title") or node.get("title") or "课堂测验"),
                                  "questions": questions})
            elif t == "flashcard" and str(raw.get("front") or "").strip():
                items.append({"type": "flashcard", "front": str(raw["front"]).strip(),
                              "back": str(raw.get("back") or "").strip(),
                              "tags": [str(t) for t in (raw.get("tags") or [])]})

    # 2) dict 形态题目（question/options/answer/explanation）→ quiz；纯文本题目 → 闪卡
    title = str(node.get("title") or "课堂测验")
    raw_questions = node.get("questions") or node.get("interactive_questions") or []
    questions = [_normalize_question(q) for q in raw_questions]
    questions = [q for q in questions if q]
    if questions:
        items.append({"type": "quiz", "title": title, "questions": questions})

    front = str(node.get("front") or "").strip()
    back = str(node.get("back") or "").strip()
    if not front and not back:
        for authored_text in (node.get("content"), node.get("summary"), node.get("script")):
            labeled = extract_front_back(authored_text)
            if labeled and all(labeled):
                front, back = labeled
                break
    back = re.sub(
        r"\s*请把正面问题与背面答案实现为可点击翻转的卡片，并嵌入\s*PPT。?\s*$",
        "",
        back,
    ).strip()
    if front and not any(item.get("type") == "flashcard" and item.get("front") == front for item in items):
        items.append({"type": "flashcard", "front": front, "back": back, "tags": []})

    # 3) segments 知识卡 → 闪卡
    flashcards: list[dict[str, Any]] = []
    for seg in node.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        kc = seg.get("knowledge_card") or {}
        term = str(kc.get("term") or kc.get("front") or "").strip()
        if term:
            flashcards.append({"type": "flashcard", "front": term,
                               "back": str(kc.get("definition") or kc.get("back") or "").strip(),
                               "tags": [str(t) for t in (kc.get("tags") or [])]})
    # 4) 纯文本题目转闪卡：正面=问题，背面=节点内容摘要（离线确定性转换，不编造答案）
    if not any(item.get("type") == "flashcard" for item in items) and not flashcards:
        for q in raw_questions:
            if isinstance(q, dict):
                continue
            text = str(q).strip()
            if not text:
                continue
            fallback_back = str(node.get("summary") or node.get("content") or node.get("script") or "").strip()[:200]
            flashcards.append({"type": "flashcard", "front": text, "back": fallback_back, "tags": ["question"]})
    items.extend(flashcards)
    return items


def extract_interactive_items(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """节点数组 → 互动素材列表（quiz / flashcard），纯规则抽取，不调用 LLM。

    输入形态兼容 dict 与 Pydantic TeachingNode（model_dump）。
    """
    extracted: list[dict[str, Any]] = []
    for node in nodes or []:
        if hasattr(node, "model_dump"):
            node = node.model_dump()
        elif hasattr(node, "dict"):
            node = node.dict()
        if isinstance(node, dict):
            extracted.extend(_node_to_items(node))
    return extracted


# ---------------------------------------------------------------------------
# HTML 渲染
# ---------------------------------------------------------------------------

def _js_data(items: list[dict[str, Any]]) -> str:
    """素材列表 → 可安全内联进 <script> 的 JSON（防 </script> 逃逸）。"""
    return json.dumps(items, ensure_ascii=False).replace("</", "<\\/")


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__PAGE_TITLE__</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
  font-family: "Microsoft YaHei", "微软雅黑", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
  background: linear-gradient(160deg, #eef3fb 0%, #dce7f7 100%);
  color: #22314e; min-height: 100vh; padding: 16px 12px 40px;
}
.wrap { max-width: 720px; margin: 0 auto; }
header.app { text-align: center; margin-bottom: 14px; }
header.app h1 { color: #16305e; font-size: 26px; letter-spacing: 1px; }
header.app .course { color: #5a6b8c; font-size: 14px; margin-top: 4px; }
.tabs { display: flex; gap: 10px; justify-content: center; margin: 12px 0 18px; }
.tabs button {
  border: 1px solid #b9c8e4; background: #fff; color: #16305e; font-size: 15px;
  padding: 9px 22px; border-radius: 22px; cursor: pointer; font-family: inherit;
  transition: all .18s ease;
}
.tabs button.active { background: #1e4a8f; border-color: #1e4a8f; color: #fff; }
.panel { display: none; }
.panel.active { display: block; }
.card {
  background: #fff; border-radius: 14px; box-shadow: 0 6px 22px rgba(22,48,94,.10);
  padding: 22px 20px;
}
.progressbar { height: 8px; background: #e3eaf6; border-radius: 4px; overflow: hidden; margin-bottom: 16px; }
.progressbar i { display: block; height: 100%; width: 0; background: linear-gradient(90deg,#1e4a8f,#3d74d6); border-radius: 4px; transition: width .3s ease; }
.meta { display: flex; justify-content: space-between; color: #5a6b8c; font-size: 13px; margin-bottom: 10px; }
.qtitle { font-size: 19px; color: #16305e; font-weight: 700; line-height: 1.55; margin-bottom: 16px; }
.options { display: grid; gap: 10px; }
.opt {
  text-align: left; border: 2px solid #d8e2f3; background: #f7faff; color: #22314e;
  border-radius: 10px; padding: 13px 15px; font-size: 15.5px; cursor: pointer;
  font-family: inherit; line-height: 1.45; transition: border-color .15s, background .15s;
}
.opt:hover { border-color: #3d74d6; }
.opt .tag { display: inline-block; font-weight: 700; color: #1e4a8f; margin-right: 8px; }
.opt.correct { border-color: #2e9e5b; background: #e9f8ef; color: #1d6b3c; animation: pop .35s ease; }
.opt.wrong { border-color: #d9534f; background: #fdecec; color: #a94442; animation: shake .35s ease; }
.opt.dim { opacity: .55; cursor: default; }
.opt:disabled { cursor: default; }
@keyframes pop { 0% { transform: scale(1); } 45% { transform: scale(1.03); } 100% { transform: scale(1); } }
@keyframes shake { 0%,100% { transform: translateX(0); } 25% { transform: translateX(-5px); } 75% { transform: translateX(5px); } }
.feedback { min-height: 24px; margin-top: 14px; font-size: 15px; font-weight: 700; }
.feedback.good { color: #2e9e5b; animation: pop .35s ease; }
.feedback.bad { color: #d9534f; }
.explain { margin-top: 8px; color: #5a6b8c; font-size: 14px; line-height: 1.6; }
.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 18px; }
.btn {
  border: none; border-radius: 22px; padding: 10px 26px; font-size: 15px; cursor: pointer;
  font-family: inherit; background: #1e4a8f; color: #fff; transition: opacity .15s;
}
.btn:disabled { opacity: .4; cursor: default; }
.btn.ghost { background: #e7eefb; color: #1e4a8f; }
.result { text-align: center; padding: 12px 0 4px; }
.result .score { font-size: 46px; color: #1e4a8f; font-weight: 800; }
.result .rate { color: #5a6b8c; font-size: 15px; margin: 8px 0 4px; }
.result .grade { display: inline-block; margin: 10px 0 18px; padding: 6px 18px; border-radius: 18px; background: #e9f8ef; color: #1d6b3c; font-size: 14px; }
/* 翻卡 */
.flip-scene { perspective: 1200px; margin: 6px 0 14px; }
.flip-card { position: relative; width: 100%; min-height: 240px; cursor: pointer; transform-style: preserve-3d; transition: transform .55s cubic-bezier(.4,.2,.2,1); }
.flip-card.flipped { transform: rotateY(180deg); }
.face {
  position: absolute; inset: 0; backface-visibility: hidden; -webkit-backface-visibility: hidden;
  border-radius: 14px; display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 26px 22px; text-align: center;
}
.face.front { background: linear-gradient(150deg,#1e4a8f,#3d74d6); color: #fff; box-shadow: 0 8px 24px rgba(30,74,143,.28); }
.face.front .term { font-size: 24px; font-weight: 700; line-height: 1.5; word-break: break-word; }
.face.front .hint { margin-top: 14px; font-size: 13px; opacity: .75; }
.face.back { background: #fff; border: 2px solid #d8e2f3; transform: rotateY(180deg); color: #22314e; justify-content: flex-start; overflow: auto; }
.face.back .def { font-size: 16px; line-height: 1.75; white-space: pre-wrap; word-break: break-word; }
.face.back .hint { margin-top: auto; padding-top: 12px; font-size: 12px; color: #8b9ab8; }
.nav { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.nav .counter { color: #5a6b8c; font-size: 14px; }
.mark { display: flex; gap: 10px; margin-top: 16px; }
.mark .btn { flex: 1; }
.mark .know { background: #2e9e5b; }
.mark .again { background: #e7eefb; color: #1e4a8f; }
.stats { display: flex; gap: 14px; justify-content: center; color: #5a6b8c; font-size: 13.5px; margin-bottom: 12px; }
.stats b { color: #1e4a8f; }
footer.app { text-align: center; color: #8b9ab8; font-size: 12px; margin-top: 22px; }
@media (max-width: 480px) {
  header.app h1 { font-size: 21px; }
  .card { padding: 18px 14px; }
  .qtitle { font-size: 17px; }
  .face.front .term { font-size: 20px; }
}
</style>
</head>
<body>
<div class="wrap">
  <header class="app">
    <h1>__TITLE__</h1>
    <div class="course">__COURSE__</div>
  </header>
  <div class="tabs" id="tabs"></div>
  <section class="panel" id="panel-quiz">
    <div class="card" id="quiz-card"></div>
  </section>
  <section class="panel" id="panel-flash">
    <div class="card" id="flash-card"></div>
  </section>
  <footer class="app">多模态 AI 互动式教学智能体 · HTML5 互动课件导出</footer>
</div>
<script>
"use strict";
var DATA = __DATA__;

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

/* ---------- 答题挑战 ---------- */
function QuizGame(container, quizzes) {
  var questions = [];
  (quizzes || []).forEach(function (qz) {
    (qz.questions || []).forEach(function (q) { questions.push(q); });
  });
  var idx = 0, score = 0, results = [], locked = false;
  var empty = questions.length === 0;

  function start() {
    idx = 0; score = 0; results = []; locked = false;
    render();
  }

  function render() {
    container.textContent = "";
    if (empty) {
      container.appendChild(el("div", "result", ""));
      container.lastChild.appendChild(el("div", "rate", "本课件暂无测验题。"));
      return;
    }
    var q = questions[idx];
    var bar = el("div", "progressbar"); var fill = el("i");
    fill.style.width = (idx / questions.length * 100) + "%"; bar.appendChild(fill);
    var meta = el("div", "meta");
    meta.appendChild(el("span", null, "第 " + (idx + 1) + " / " + questions.length + " 题"));
    meta.appendChild(el("span", null, "当前得分：" + score));
    container.appendChild(bar);
    container.appendChild(meta);
    container.appendChild(el("div", "qtitle", q.question));
    var box = el("div", "options");
    var letters = "ABCDEFGH";
    q.options.forEach(function (opt, i) {
      var b = el("button", "opt");
      b.appendChild(el("span", "tag", letters[i] + "."));
      b.appendChild(document.createTextNode(opt));
      b.addEventListener("click", function () { answer(i, box, q); });
      box.appendChild(b);
    });
    container.appendChild(box);
    var fb = el("div", "feedback"); container.appendChild(fb);
    var ex = el("div", "explain"); container.appendChild(ex);
    var actions = el("div", "actions");
    var next = el("button", "btn", idx === questions.length - 1 ? "查看成绩" : "下一题");
    next.disabled = true;
    next.addEventListener("click", function () {
      if (idx === questions.length - 1) { finish(); } else { idx++; render(); }
    });
    actions.appendChild(next);
    container.appendChild(actions);
  }

  function answer(i, box, q) {
    if (locked) return;
    locked = true;
    var buttons = box.querySelectorAll(".opt");
    var hasKey = (q.answer === 0 || q.answer > 0) && q.answer < 8;
    for (var k = 0; k < buttons.length; k++) {
      buttons[k].disabled = true;
      if (hasKey && k === q.answer) buttons[k].classList.add("correct");
      else if (k === i && hasKey) buttons[k].classList.add("wrong");
      else if (k === i) buttons[k].classList.add("correct");
      else buttons[k].classList.add("dim");
    }
    var fb = container.querySelector(".feedback");
    if (!hasKey) {
      // 无标准答案（LLM 输出无法识别）：不强判对错，只记录选择
      fb.classList.add("good"); fb.textContent = "已提交你的选择。";
      results.push(true);
    } else {
      var ok = i === q.answer;
      if (ok) { score++; fb.classList.add("good"); fb.textContent = "回答正确！"; }
      else { fb.classList.add("bad"); fb.textContent = "回答错误，正确答案是 " + "ABCDEFGH"[q.answer] + "。"; }
      results.push(ok);
    }
    var ex = container.querySelector(".explain");
    if (q.explanation) ex.textContent = "解析：" + q.explanation;
    container.querySelector(".actions .btn").disabled = false;
  }

  function finish() {
    container.textContent = "";
    var total = questions.length;
    var rate = total ? Math.round(score / total * 100) : 0;
    var grade = rate >= 90 ? "优秀 · 已掌握本节要点" : rate >= 60 ? "良好 · 再巩固薄弱处" : "继续加油 · 建议复习知识卡";
    var res = el("div", "result");
    res.appendChild(el("div", "score", score + " / " + total));
    res.appendChild(el("div", "rate", "正确率 " + rate + "%"));
    res.appendChild(el("div", "grade", grade));
    var restart = el("button", "btn", "重新开始");
    restart.addEventListener("click", start);
    res.appendChild(restart);
    container.appendChild(res);
  }

  start();
}

/* ---------- 知识翻卡 ---------- */
function FlashGame(container, cards) {
  var deck = [];
  (cards || []).forEach(function (c) {
    deck.push({ front: c.front, back: c.back || "", tags: c.tags || [] });
  });
  var idx = 0, known = [], review = [];
  var empty = deck.length === 0;

  function start() {
    idx = 0; known = []; review = [];
    render();
  }

  function render() {
    container.textContent = "";
    if (empty) {
      container.appendChild(el("div", "result", ""));
      container.lastChild.appendChild(el("div", "rate", "本课件暂无知识卡。"));
      return;
    }
    var stats = el("div", "stats");
    var s1 = el("span"); s1.appendChild(document.createTextNode("已掌握 ")); s1.appendChild(el("b", null, String(known.length)));
    var s2 = el("span"); s2.appendChild(document.createTextNode("待巩固 ")); s2.appendChild(el("b", null, String(review.length)));
    stats.appendChild(s1); stats.appendChild(s2);
    container.appendChild(stats);

    var scene = el("div", "flip-scene");
    var card = el("div", "flip-card");
    var front = el("div", "face front");
    front.appendChild(el("div", "term", deck[idx].front));
    front.appendChild(el("div", "hint", "点击卡片查看释义"));
    var back = el("div", "face back");
    back.appendChild(el("div", "def", deck[idx].back || "（暂无释义）"));
    back.appendChild(el("div", "hint", "再次点击返回正面"));
    card.appendChild(front); card.appendChild(back);
    card.addEventListener("click", function () { card.classList.toggle("flipped"); });
    scene.appendChild(card);
    container.appendChild(scene);

    var nav = el("div", "nav");
    var prev = el("button", "btn ghost", "上一张");
    var counter = el("span", "counter", (idx + 1) + " / " + deck.length);
    var next = el("button", "btn ghost", "下一张");
    prev.disabled = idx === 0;
    next.disabled = idx === deck.length - 1;
    prev.addEventListener("click", function () { if (idx > 0) { idx--; render(); } });
    next.addEventListener("click", function () { if (idx < deck.length - 1) { idx++; render(); } });
    nav.appendChild(prev); nav.appendChild(counter); nav.appendChild(next);
    container.appendChild(nav);

    var mark = el("div", "mark");
    var know = el("button", "btn know", "我记住了");
    var again = el("button", "btn again", "再看看");
    know.addEventListener("click", function () { markCard(true); });
    again.addEventListener("click", function () { markCard(false); });
    mark.appendChild(know); mark.appendChild(again);
    container.appendChild(mark);
  }

  function markCard(remembered) {
    if (remembered) known.push(deck[idx]); else review.push(deck[idx]);
    if (idx < deck.length - 1) { idx++; render(); } else { finish(); }
  }

  function finish() {
    container.textContent = "";
    var res = el("div", "result");
    res.appendChild(el("div", "score", known.length + " / " + deck.length));
    res.appendChild(el("div", "rate", "已掌握 " + known.length + " 张，待巩固 " + review.length + " 张"));
    if (review.length) {
      var box = el("div", "explain");
      box.style.margin = "10px 0 16px";
      box.textContent = "待巩固：" + review.map(function (c) { return c.front; }).join("、");
      res.appendChild(box);
    }
    var restart = el("button", "btn", "重新复习");
    restart.addEventListener("click", start);
    res.appendChild(restart);
    container.appendChild(res);
  }

  start();
}

/* ---------- 模式装配 ---------- */
(function init() {
  var quizzes = DATA.filter(function (x) { return x.type === "quiz"; });
  var cards = DATA.filter(function (x) { return x.type === "flashcard"; });
  var tabs = document.getElementById("tabs");
  var panels = { quiz: document.getElementById("panel-quiz"), flash: document.getElementById("panel-flash") };
  var modes = [];
  if (quizzes.length) modes.push("quiz");
  if (cards.length) modes.push("flash");

  var labels = { quiz: "答题挑战", flash: "知识翻卡" };
  if (modes.length > 1) {
    modes.forEach(function (m, i) {
      var b = el("button", i === 0 ? "active" : "", labels[m]);
      b.addEventListener("click", function () {
        tabs.querySelectorAll("button").forEach(function (x) { x.classList.remove("active"); });
        b.classList.add("active");
        Object.keys(panels).forEach(function (k) {
          panels[k].classList.toggle("active", k === m);
        });
      });
      tabs.appendChild(b);
    });
  }
  var first = modes[0] || "quiz";
  if (modes.length) panels[first].classList.add("active");
  QuizGame(document.getElementById("quiz-card"), quizzes);
  FlashGame(document.getElementById("flash-card"), cards);
})();
</script>
</body>
</html>
"""


class ExportHTML5Config:
    """HTML5 导出配置"""
    output_dir: str = "data/exports"


def _empty_items_page(course_name: str, title: str) -> str:
    """无互动物料时的占位页（保持单文件自包含与统一风格）。"""
    return (_HTML_TEMPLATE
            .replace("__DATA__", "[]")
            .replace("__TITLE__", escape(title))
            .replace("__COURSE__", escape(course_name))
            .replace("__PAGE_TITLE__", escape(title)))


def render_interactive_html(
    items: list[dict[str, Any]],
    course_name: str = "课件",
    title: str = "互动课堂",
) -> str:
    """互动素材列表 → 单文件自包含 HTML5 小游戏。

    Args:
        items: interactive.py 产出的素材列表，支持
               ``{"type": "quiz", "title": ..., "questions": [{question, options, answer, explanation}]}``
               与 ``{"type": "flashcard", "front", "back", "tags"}``；
               也兼容扁平形态 ``{"type": "flashcard", ...}`` 直接平铺。
        course_name: 课程名（页眉副标题）
        title: 页面主标题

    Returns:
        完整 HTML 文本（内联 CSS+JS，零外部依赖）
    """
    normalized: list[dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        t = str(raw.get("type") or "").lower()
        if t == "quiz":
            questions = [_normalize_question(q) for q in raw.get("questions") or []]
            questions = [q for q in questions if q]
            if questions:
                normalized.append({"type": "quiz", "title": str(raw.get("title") or title), "questions": questions})
        elif t == "flashcard":
            front = str(raw.get("front") or "").strip()
            if front:
                normalized.append({"type": "flashcard", "front": front,
                                   "back": str(raw.get("back") or "").strip(),
                                   "tags": [str(x) for x in (raw.get("tags") or [])]})
        # vote 等其他类型暂不入游戏（赛题 4c 要求至少一种，quiz/flashcard 已覆盖）

    html = (_HTML_TEMPLATE
            .replace("__DATA__", _js_data(normalized))
            .replace("__TITLE__", escape(title))
            .replace("__COURSE__", escape(course_name))
            .replace("__PAGE_TITLE__", escape(title)))
    return html


def export_interactive_html(
    nodes: list[dict[str, Any]],
    course_name: str = "课件",
    output_dir: str = "data/exports",
    file_name: str = "interactive.html",
) -> dict[str, Any]:
    """节点数组 → HTML5 互动游戏文件（供导出任务调用）。

    Returns:
        {"path": 输出路径, "quiz_count": N, "flashcard_count": N, "file_size": N}
    """
    items = extract_interactive_items(nodes)
    has_quiz = any(i.get("type") == "quiz" for i in items)
    has_flash = any(i.get("type") == "flashcard" for i in items)
    title = "答题挑战 · 知识翻卡" if (has_quiz and has_flash) else (
        "答题挑战" if has_quiz else "知识翻卡")
    html = render_interactive_html(items, course_name=course_name, title=title)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / file_name
    path.write_text(html, encoding="utf-8")
    return {
        "path": str(path),
        "quiz_count": sum(1 for i in items if i.get("type") == "quiz"),
        "flashcard_count": sum(1 for i in items if i.get("type") == "flashcard"),
        "file_size": path.stat().st_size,
    }
