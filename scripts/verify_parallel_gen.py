"""离线验证脚本：Stage3 讲稿分块并行生成（不联网、不消耗 LLM 额度）

验证目标（对应 ai_engine/generator.py 的 _run_stage3_enhanced_scripts 改造）：
  1. 8 个节点按 LLM_GEN_CHUNK_SIZE=3 切成 3 块（3 次 Stage3 LLM 调用，而非 1 次巨型调用）
  2. 并行执行：总耗时 ≈ max(块耗时) 而非 sum（用 0.5s/块的桩延迟验证峰值并发）
  3. 某一块抛异常（桩内模拟重试后仍失败）时其余块正常，失败块节点走 fallback
  4. progress_cb 被调用且次数合理（Stage1/Stage2 各 1 次 + 每块完成各 1 次）
  5. 各块结果合并后 node_id 齐全、与节点树一一对应

实现方式：
  - monkeypatch LessonGenerator._run_stage1_markdown_understanding / _run_stage2_node_tree
    返回固定结果，跳过前两阶段；
  - monkeypatch LessonGenerator._build_llm_client 返回哑 client；
  - monkeypatch LessonGenerator._request_llm_payload 桩函数：解析 user_prompt 中的
    「本块节点 node_id 列表」，模拟 0.5s 延迟后返回该块节点的合法 scripts JSON；
    并记录调用次数、每块节点数与峰值并发度（全程无真实网络调用）。

运行：python scripts/verify_parallel_gen.py
"""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 必须在导入 ai_engine 前设置：强制走真实调用分支（出口已被 monkeypatch，不联网）
os.environ["AI_GEN_MODE"] = "llm"
os.environ.setdefault("AI_API_KEY", "offline-verify-key")
os.environ["LLM_GEN_CHUNK_SIZE"] = "3"
os.environ["LLM_GEN_MAX_WORKERS"] = "3"

from ai_engine.generator import LessonGenerator  # noqa: E402
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


# ---------------- 桩：记录并发度与调用次数，模拟 0.5s 延迟 ----------------

class Stage3Recorder:
    """记录 Stage3 分块调用信息，并可指定某些 node_id 所在块直接抛异常。"""

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
                    raise RuntimeError("simulated chunk failure after retries")
                time.sleep(self.delay)
                return json.dumps({"scripts": self._fake_chunk_scripts(chunk_ids)}, ensure_ascii=False)
            finally:
                with self.call_lock:
                    self.active -= 1
        return stub


def build_generator_with_8_nodes():
    gen = LessonGenerator()
    md = "\n".join(f"## 小节{i}\n\n小节{i}的内容要点。" for i in range(1, 9))
    nodes = gen._fallback_pipeline(md)["node_tree"]["nodes"]
    assert len(nodes) == 8, f"预期 8 个节点，实际 {len(nodes)}"
    return gen, nodes


def run_case(recorder, nodes):
    gen = LessonGenerator()
    progress_events = []

    gen._build_llm_client = lambda: object()  # 哑 client（worker 线程内新建也会走这里）
    gen._run_stage1_markdown_understanding = lambda client, markdown: {
        "normalized_markdown": "normalized", "key_points": ["kp1"],
    }
    gen._run_stage2_node_tree = lambda client, markdown, key_points: list(nodes)
    gen._request_llm_payload = recorder.request_llm_payload(gen._request_llm_payload)

    start = time.perf_counter()
    result = gen.generate_from_markdown_enhanced(
        "md-content", "测试课程",
        progress_cb=lambda pct, msg: progress_events.append((pct, msg)),
    )
    elapsed = time.perf_counter() - start
    return gen, result, progress_events, elapsed


def main():
    print("=" * 64)
    print("Stage3 分块并行生成 离线验证")
    print("=" * 64)

    cfg_ok = check(
        "配置解析: LLM_GEN_CHUNK_SIZE=3 / LLM_GEN_MAX_WORKERS=3",
        resolve_llm_gen_chunk_size() == 3 and resolve_llm_gen_max_workers() == 3,
    )
    if not cfg_ok:
        print("FAIL - 配置解析异常，终止后续用例")
        return 1

    # ---- 用例 1/2/4/5：8 节点全部成功，3 块并行 ----
    gen, nodes = build_generator_with_8_nodes()
    recorder = Stage3Recorder()
    _, result, progress_events, elapsed = run_case(recorder, nodes)

    chunk_sizes = [len(c) for c in recorder.calls]
    check("① 8节点被切成3块（3次Stage3调用，块大小3/3/2）",
          len(recorder.calls) == 3 and chunk_sizes == [3, 3, 2],
          f"calls={len(recorder.calls)}, sizes={chunk_sizes}")

    # sum(块耗时)=1.5s；并行应 ≈ max=0.5s，留裕量断言 < 1.4s 且峰值并发 ≥ 2
    check("② 并行执行：总耗时≈max(块耗时) 而非 sum",
          elapsed < 1.4 and recorder.peak_concurrency >= 2,
          f"elapsed={elapsed:.2f}s (sum=1.50s), peak_concurrency={recorder.peak_concurrency}")

    stage3_progress = [e for e in progress_events if "Stage3" in e[1]]
    check("④ progress_cb 被调用且次数合理（55/60 各1次 + 每块完成1次）",
          any(abs(p[0] - 55.0) < 1e-6 for p in progress_events)
          and any(abs(p[0] - 60.0) < 1e-6 for p in progress_events)
          and len(stage3_progress) == 3,
          f"events={[(round(p,1), m) for p, m in progress_events]}")

    result_ids = [s["node_id"] for s in result.get("scripts", [])]
    expected_ids = [n["node_id"] for n in nodes]
    check("⑤ 合并后 node_id 齐全且与节点树一一对应",
          result_ids == expected_ids and not result.get("used_fallback"),
          f"got {len(result_ids)} scripts, expected {expected_ids}")

    # ---- 用例 3：中间块（含 node_004）失败 → 该块走 fallback，其余块正常 ----
    gen2, nodes2 = build_generator_with_8_nodes()
    fail_recorder = Stage3Recorder(fail_node_ids={"node_004"})
    _, result2, progress_events2, elapsed2 = run_case(fail_recorder, nodes2)

    scripts2 = {s["node_id"]: s for s in result2.get("scripts", [])}
    failed_chunk_node_ids = {nid for c in fail_recorder.failed_chunks for nid in c}
    fallback_ok = all(
        scripts2.get(nid, {}).get("script", "").startswith("讲解节点")
        for nid in failed_chunk_node_ids
    )
    others_ok = all(
        nid in scripts2 and not scripts2[nid]["script"].startswith("讲解节点")
        for c in fail_recorder.calls
        for nid in c
        if nid not in failed_chunk_node_ids
    )
    check("③ 某块失败：失败块节点走 fallback，其余块正常、node_id 齐全",
          failed_chunk_node_ids == {"node_004", "node_005", "node_006"}
          and fallback_ok and others_ok
          and set(scripts2.keys()) == {n["node_id"] for n in nodes2},
          f"failed_chunk={sorted(failed_chunk_node_ids)}, "
          f"scripts={len(scripts2)}, elapsed={elapsed2:.2f}s")

    print("=" * 64)
    if FAIL_RESULTS:
        print(f"RESULT: FAIL（{len(FAIL_RESULTS)} 项未通过 / {len(PASS_RESULTS)} 项通过）")
        return 1
    print(f"RESULT: PASS（全部 {len(PASS_RESULTS)} 项通过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
