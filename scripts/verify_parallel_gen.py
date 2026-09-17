"""离线验证脚本：S3 提速改造（不联网、不消耗 LLM 额度）

验证目标（对应 ai_engine/generator.py 与 ai_engine/core/llm.py 的提速改造）：
  ① 规整 markdown（≥300 字符且含 ≥2 个二级标题）跳过 Stage1（Stage1 LLM 调用次数=0，
     原文直接进 Stage2，progress 55 立即触发且消息标注跳过）
  ② 乱输入仍走 Stage1 清洗（调用次数=1）
  ③ 8 节点按 LLM_GEN_CHUNK_SIZE=1 切成 8 块并行（8 次 Stage3 调用，
     peak concurrency ≤ LLM_GEN_MAX_WORKERS=4 且 ≥2）
  ④ 某节点失败仅该节点走 fallback，其余节点正常
  ⑤ progress 单调不减
  ⑥ chat_with_schema 降级链：一级 json_schema 400 → 二级 json_object 成功
     （断言 json_object 被使用且结果正确、无同级重试）

实现方式：
  - monkeypatch LessonGenerator._run_stage1_markdown_understanding /
    _run_stage2_node_tree / _build_llm_client / _request_llm_payload，
    全程无真实网络调用；
  - ⑥ monkeypatch LLMClient._post_chat_completions（真正 HTTP 出口）+
    llm 模块 time.sleep（记录退避并跳过真实等待）。

运行：python scripts/verify_parallel_gen.py
"""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 必须在导入 ai_engine 前设置：强制走真实调用分支（出口已被 monkeypatch，不联网）
os.environ["AI_GEN_MODE"] = "llm"
os.environ.setdefault("AI_API_KEY", "offline-verify-key")
os.environ["LLM_GEN_CHUNK_SIZE"] = "1"
os.environ["LLM_GEN_MAX_WORKERS"] = "4"

from ai_engine.generator import LessonGenerator  # noqa: E402
from ai_engine.core import llm as llm_mod  # noqa: E402
from ai_engine.core.config import (  # noqa: E402
    resolve_llm_gen_chunk_size,
    resolve_llm_gen_max_workers,
)

PASS_RESULTS = []
FAIL_RESULTS = []


def check(name, cond, detail=""):
    (PASS_RESULTS if cond else FAIL_RESULTS).append((name, detail))
    tag = "PASS" if cond else "FAIL"
    line = f"{tag} - {name}"
    if detail:
        line += f"  [{detail}]"
    print(line)
    return cond


# ---------------- Stage1/Stage2 记录桩 ----------------

class Stage1Recorder:
    """记录 Stage1 调用次数，返回固定的清洗结果。"""

    def __init__(self):
        self.calls = 0

    def stub(self, client, markdown):
        self.calls += 1
        return {"normalized_markdown": "cleaned-by-stage1", "key_points": ["kp1", "kp2"]}


# ---------------- Stage3 桩：记录并发度与调用次数，模拟 0.5s 延迟 ----------------

class Stage3Recorder:
    """记录 Stage3 分块调用信息，并可指定某些 node_id 直接抛异常。"""

    def __init__(self, fail_node_ids=(), delay=0.5):
        self.calls = []          # 每次调用的 chunk node_id 列表
        self.call_lock = threading.Lock()
        self.active = 0
        self.peak_concurrency = 0
        self.delay = delay
        self.fail_node_ids = set(fail_node_ids)
        self.failed_chunks = []

    def _fake_chunk_scripts(self, chunk_ids):
        scripts = []
        for i, nid in enumerate(chunk_ids, start=1):
            scripts.append({
                "node_id": nid,
                "title": f"节点{nid}",
                "script": f"这是{nid}的并行生成讲稿。",
                "segments": [{
                    "segment_id": f"seg_{nid}_1",
                    "text": f"这是{nid}的并行生成讲稿正文。",
                    "node_id": nid,
                    "segment_type": "explanation",
                    "estimated_seconds": 40,
                    "interaction_hint": f"请举例说明{nid}。",
                    "knowledge_card": {"term": nid, "definition": "定义", "formula": "", "tags": []},
                    "difficulty": "medium",
                }],
            })
        return scripts

    def request_llm_payload(self, orig_func):
        def stub(client, system_prompt, user_prompt, *args, **kwargs):
            m = re.search(r"本块节点 node_id 列表: (\[.*?\])", user_prompt)
            chunk_ids = json.loads(m.group(1)) if m else []
            with self.call_lock:
                self.calls.append(list(chunk_ids))
                should_fail = bool(self.fail_node_ids & set(chunk_ids))
                if should_fail:
                    self.failed_chunks.append(list(chunk_ids))
                self.active += 1
                self.peak_concurrency = max(self.peak_concurrency, self.active)
            try:
                if should_fail:
                    raise RuntimeError("simulated node failure after retries")
                time.sleep(self.delay)
                return json.dumps({"scripts": self._fake_chunk_scripts(chunk_ids)}, ensure_ascii=False)
            finally:
                with self.call_lock:
                    self.active -= 1
        return stub


def build_8_nodes():
    md = "\n".join(f"## 小节{i}\n\n小节{i}的内容要点。" for i in range(1, 9))
    nodes = LessonGenerator()._fallback_pipeline(md)["node_tree"]["nodes"]
    assert len(nodes) == 8, f"预期 8 个节点，实际 {len(nodes)}"
    return nodes


def patch_generation(gen, stage1_recorder, nodes, stage3_recorder):
    """统一打桩：Stage1 记录、Stage2 固定、LLM 出口替换为 Stage3 桩。"""
    gen._build_llm_client = lambda: object()  # 哑 client（worker 线程内新建也会走这里）
    gen._run_stage1_markdown_understanding = stage1_recorder.stub
    gen._run_stage2_node_tree = lambda client, markdown, key_points: list(nodes)
    gen._request_llm_payload = stage3_recorder.request_llm_payload(gen._request_llm_payload)


def run_generation(gen, markdown):
    progress_events = []
    start = time.perf_counter()
    result = gen.generate_from_markdown_enhanced(
        markdown, "测试课程",
        progress_cb=lambda pct, msg: progress_events.append((pct, msg)),
    )
    elapsed = time.perf_counter() - start
    return result, progress_events, elapsed


def build_regular_markdown() -> str:
    """规整 markdown：≥300 字符 + 3 个二级标题。"""
    lines = ["# 高数绪论"]
    for i in range(1, 4):
        lines.append(f"## 小节{i}")
        lines.append(f"这是第{i}节的正文内容，包含定义、定理与例题的完整描述，" * 4)
    return "\n".join(lines)


def main():
    print("=" * 64)
    print("S3 提速改造 离线验证（跳过 Stage1 / 每节点并行 / 降级链）")
    print("=" * 64)

    check("配置解析: LLM_GEN_CHUNK_SIZE=1 / LLM_GEN_MAX_WORKERS=4",
          resolve_llm_gen_chunk_size() == 1 and resolve_llm_gen_max_workers() == 4,
          f"chunk={resolve_llm_gen_chunk_size()}, workers={resolve_llm_gen_max_workers()}")

    # ---- ① 规整 markdown 跳过 Stage1 ----
    gen1 = LessonGenerator()
    nodes1 = build_8_nodes()
    rec1 = Stage1Recorder()
    rec3_a = Stage3Recorder(delay=0)
    patch_generation(gen1, rec1, nodes1, rec3_a)
    regular_md = build_regular_markdown()
    result1, progress1, _ = run_generation(gen1, regular_md)

    check("① 规整输入 Stage1 调用次数=0（跳过）", rec1.calls == 0, f"stage1_calls={rec1.calls}")
    check("① 规整输入原文直进 Stage2（source_markdown==原文）",
          result1.get("source_markdown") == regular_md,
          f"len={len(str(result1.get('source_markdown') or ''))}")
    check("① 跳过时 55 进度立即触发且消息标注跳过",
          any(abs(p - 55.0) < 1e-6 and "跳过" in m for p, m in progress1),
          f"stage1_events={[(p, m) for p, m in progress1 if abs(p - 55.0) < 1e-6]}")
    check("① 跳过时从标题本地提取关键点（非空）",
          bool(result1.get("key_points")), f"key_points={result1.get('key_points')}")

    # ---- ② 乱输入仍走 Stage1 ----
    gen2 = LessonGenerator()
    rec2 = Stage1Recorder()
    rec3_b = Stage3Recorder(delay=0)
    patch_generation(gen2, rec2, nodes1, rec3_b)
    result2, progress2, _ = run_generation(gen2, "随便一段没有结构的话，没有标题也没有足够长度。")

    check("② 乱输入 Stage1 调用次数=1", rec2.calls == 1, f"stage1_calls={rec2.calls}")
    check("② 乱输入使用 Stage1 清洗结果", result2.get("source_markdown") == "cleaned-by-stage1",
          f"source={str(result2.get('source_markdown'))[:30]}")

    # ---- ③ 8 节点切成 8 块并行（peak ≤ 4）+ ⑤ progress 单调不减 ----
    gen3 = LessonGenerator()
    nodes3 = build_8_nodes()
    rec3_c = Stage3Recorder(delay=0.5)
    patch_generation(gen3, Stage1Recorder(), nodes3, rec3_c)
    result3, progress3, elapsed3 = run_generation(gen3, build_regular_markdown())

    chunk_sizes = [len(c) for c in rec3_c.calls]
    check("③ 8节点切成8块（8次Stage3调用，每块1节点）",
          len(rec3_c.calls) == 8 and chunk_sizes == [1] * 8,
          f"calls={len(rec3_c.calls)}, sizes={set(chunk_sizes)}")
    check("③ 并行受 worker 上限约束（2 ≤ peak ≤ 4）且总耗时≈max 而非 sum",
          2 <= rec3_c.peak_concurrency <= 4 and elapsed3 < 2.5,
          f"peak={rec3_c.peak_concurrency}, elapsed={elapsed3:.2f}s (sum=4.00s)")
    check("③ 合并后 node_id 齐全且与节点树一一对应",
          [s["node_id"] for s in result3.get("scripts", [])] == [n["node_id"] for n in nodes3]
          and not result3.get("used_fallback"),
          f"scripts={len(result3.get('scripts', []))}")

    pcts = [p for p, _ in progress3]
    check("⑤ progress 单调不减",
          all(pcts[i + 1] >= pcts[i] - 1e-9 for i in range(len(pcts) - 1)),
          f"pcts={[round(p, 2) for p in pcts]}")

    # ---- ④ 某节点失败仅该节点 fallback ----
    gen4 = LessonGenerator()
    nodes4 = build_8_nodes()
    rec3_d = Stage3Recorder(fail_node_ids={"node_004"}, delay=0)
    patch_generation(gen4, Stage1Recorder(), nodes4, rec3_d)
    result4, _, _ = run_generation(gen4, build_regular_markdown())

    scripts4 = {s["node_id"]: s for s in result4.get("scripts", [])}
    failed_ids = {nid for c in rec3_d.failed_chunks for nid in c}
    fallback_ok = failed_ids == {"node_004"} and scripts4["node_004"]["script"].startswith("讲解节点")
    others_ok = all(
        nid in scripts4 and not scripts4[nid]["script"].startswith("讲解节点")
        for nid in (n["node_id"] for n in nodes4) if nid != "node_004"
    )
    check("④ node_004 失败仅该节点走 fallback，其余正常、node_id 齐全",
          fallback_ok and others_ok and set(scripts4.keys()) == {n["node_id"] for n in nodes4},
          f"failed={sorted(failed_ids)}, scripts={len(scripts4)}")

    # ---- ⑥ chat_with_schema 降级链：一级 json_schema 400 → 二级 json_object 成功 ----
    formats_used = []
    calls_6 = {"n": 0}
    schema = {"name": "node_tree", "strict": True,
              "schema": {"type": "object", "properties": {"nodes": {"type": "array"}},
                         "required": ["nodes"]}}
    good_payload = json.dumps({"nodes": [{"node_id": "node_001", "title": "导数定义"}]}, ensure_ascii=False)

    def fake_post_6(self, messages, actual_model, actual_temperature, **kw):
        calls_6["n"] += 1
        rf = kw.get("response_format") or {}
        formats_used.append(rf.get("type") or "none")
        if rf.get("type") == "json_schema":
            raise Exception("Error code: 400 - response_format json_schema not supported by this gateway")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=good_payload))],
            usage=None,
        )

    sleeps_6 = []
    original_post = llm_mod.LLMClient._post_chat_completions
    original_time = llm_mod.time
    llm_mod.LLMClient._post_chat_completions = fake_post_6
    llm_mod.time = SimpleNamespace(sleep=sleeps_6.append)
    try:
        client = llm_mod.LLMClient()
        result6 = client.chat_with_schema("系统提示", "用户消息", schema, temperature=0.2)
    finally:
        llm_mod.LLMClient._post_chat_completions = original_post
        llm_mod.time = original_time

    check("⑥ 一级 json_schema 400 后降级到二级 json_object（结果正确）",
          result6 == {"nodes": [{"node_id": "node_001", "title": "导数定义"}]},
          f"result={result6}")
    check("⑥ 请求形态序列为 [json_schema, json_object]（json_object 被使用）",
          formats_used == ["json_schema", "json_object"],
          f"formats={formats_used}")
    check("⑥ 400 不可重试：无同级重复重试、无退避等待（总调用=2，sleep=0）",
          calls_6["n"] == 2 and sleeps_6 == [],
          f"calls={calls_6['n']}, sleeps={sleeps_6}")

    # ---- 汇总 ----
    print("=" * 64)
    if FAIL_RESULTS:
        print(f"RESULT: FAIL（{len(FAIL_RESULTS)} 项未通过 / {len(PASS_RESULTS)} 项通过）")
        return 1
    print(f"RESULT: PASS（全部 {len(PASS_RESULTS)} 项通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
