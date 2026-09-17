"""M4-5 批量生成压测 + 内容充实度抽检脚本

两种模式：
  mock（默认）：进程内注入 AI_GEN_MODE=mock（不改 .env），连续对 S3 生成管线
               （outline → nodes → 讲稿 → 快照落盘）做 N 次调用，断言：
                 1) 每次任务达到 done 状态
                 2) 无未捕获异常
                 3) 每份快照 JSON 落盘合法（可解析、nodes_snapshot 为列表）
  llm（可选） ：AI_GEN_MODE=llm，真实调用 LLM API —— 会消耗额度，脚本会先提醒。

充实度统计：对每份快照逐节点统计 script + segments.text 总字数，
低于 300 字标记「内容不足」，最后打印统计表。

实现方式：函数级调用（不走 HTTP）。直接导入 ai_engine.main，
复刻 gen/create 的任务构造，同步调用 _run_generation_pipeline，
避免占用端口 / 依赖 uvicorn，比起子进程 HTTP 方式更稳。

运行（仓库根目录）：
  export PYTHONIOENCODING=utf-8
  python scripts/stress_test_generation.py                 # mock，5 次
  python scripts/stress_test_generation.py --runs 3        # mock，3 次
  python scripts/stress_test_generation.py --mode llm      # 真实调用（耗额度）
可选：--clean 压测后删除本次测试产生的 data/versions/{gen_id} 目录。
"""

import argparse
import json
import os
import shutil
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AI_ENGINE_DIR = REPO_ROOT / "ai_engine"

CONTENT_MIN_CHARS = 300  # 低于该字数的节点标记「内容不足」


def parse_args():
    parser = argparse.ArgumentParser(description="S3 批量生成压测 + 内容充实度抽检")
    parser.add_argument("--mode", choices=["mock", "llm"], default="mock",
                        help="mock=离线兜底链路（默认）；llm=真实调用 LLM（消耗额度）")
    parser.add_argument("--runs", type=int, default=5, help="连续生成次数（默认 5）")
    parser.add_argument("--topic", default="排序算法", help="生成主题")
    parser.add_argument("--clean", action="store_true",
                        help="压测结束后删除本次测试产生的快照目录")
    return parser.parse_args()


def node_content_chars(node: dict) -> int:
    """单节点内容字数：script + 所有 segments.text。"""
    total = len(str(node.get("script") or ""))
    for seg in node.get("segments") or []:
        total += len(str(seg.get("text") or ""))
    return total


def main() -> int:
    args = parse_args()

    if args.mode == "llm":
        print("=" * 64)
        print("!! 额度提醒：--mode llm 将真实调用 LLM API（AI_BASE_URL 所配服务）")
        print("!! 每次生成约产生 2N+1 次 LLM 请求（大纲 + 逐节点讲稿 + 兜底），")
        print("!! 会消耗 API 额度。如非必要请使用默认 mock 模式。")
        print("=" * 64)

    # ---- 环境注入（进程内覆盖，不改 .env）；必须在 import ai_engine 之前 ----
    os.environ["AI_GEN_MODE"] = args.mode
    os.environ.setdefault("REDIS_ENABLED", "0")  # 离线压测，禁用 Redis 依赖，走内存回退
    os.chdir(AI_ENGINE_DIR)  # gen/version.py 使用相对路径 data/versions
    sys.path.insert(0, str(REPO_ROOT))

    from ai_engine import main as engine
    from ai_engine.core.schema import GenerationCreateRequest

    snapshot_root = AI_ENGINE_DIR / "data" / "versions"
    created_gen_dirs = []
    records = []
    uncaught = 0
    status_pass = 0

    print("=" * 64)
    print(f"压测开始: mode={args.mode}, runs={args.runs}, topic={args.topic}")
    print(f"快照目录: {snapshot_root}")
    print("=" * 64)

    for i in range(1, args.runs + 1):
        run_tag = f"run#{i:02d}"
        task_id = f"stress_{uuid.uuid4().hex[:10]}"
        gen_id = f"course_stress_{uuid.uuid4().hex[:10]}"
        req = GenerationCreateRequest(
            session_id=f"stress-session-{i}",
            course_id=f"stress-course-{i}",
            title=f"{args.topic}（压测 {run_tag}）",
            markdown="",
            intent={
                "topic": args.topic,
                "duration_minutes": 45,
                "target_student": "大一计算机专业",
                "knowledge_points": ["冒泡排序", "快速排序", "归并排序"],
                "output_format": ["ppt"],
                "with_interactive": True,
            },
        )

        # 复刻 gen/create 的任务构造（同步线程内直接跑管道）
        task = engine.GenerationTask(
            task_id=task_id,
            session_id=req.session_id,
            generation_id=gen_id,
            status=engine.GenerationStatus.PENDING,
            stage=engine.GenerationStage.INTENT_LOCKED,
            progress_pct=0.0,
            intent=req.intent,
            evidence=req.evidence_packet,
            template_id=req.template_id,
            nodes=[],
            created_at=datetime.now(),
        )
        with engine._gen_tasks_lock:
            engine._gen_tasks[task_id] = task

        start = time.time()
        try:
            engine._run_generation_pipeline(task_id, req)
        except Exception:
            uncaught += 1
            print(f"[{run_tag}] 未捕获异常:")
            traceback.print_exc()

        task = engine._gen_tasks.get(task_id)
        elapsed = time.time() - start
        status_value = getattr(getattr(task, "status", None), "value", str(getattr(task, "status", "?")))
        done = bool(task) and task.status == engine.GenerationStatus.DONE and not getattr(task, "error", None)
        if done:
            status_pass += 1

        # 快照落盘校验
        gen_dir = snapshot_root / gen_id
        created_gen_dirs.append(gen_dir)
        snapshot_files = sorted(gen_dir.glob("v_*.json")) if gen_dir.exists() else []
        snap_ok = False
        snap_nodes = []
        snap_error = ""
        if snapshot_files:
            try:
                with open(snapshot_files[-1], "r", encoding="utf-8") as f:
                    snap = json.load(f)
                snap_nodes = snap.get("nodes_snapshot") or []
                snap_ok = isinstance(snap_nodes, list) and len(snap_nodes) > 0
            except Exception as exc:
                snap_error = f"{type(exc).__name__}: {exc}"
        else:
            snap_error = "快照文件不存在"

        # 充实度统计
        node_stats = []
        for node in snap_nodes:
            chars = node_content_chars(node)
            node_stats.append({
                "node_id": str(node.get("node_id") or "?"),
                "title": str(node.get("title") or "")[:18],
                "chars": chars,
                "low": chars < CONTENT_MIN_CHARS,
            })
        total_chars = sum(s["chars"] for s in node_stats)
        avg_chars = round(total_chars / len(node_stats), 1) if node_stats else 0
        low_count = sum(1 for s in node_stats if s["low"])

        records.append({
            "run": run_tag, "task_id": task_id, "gen_id": gen_id,
            "status": status_value, "done": done, "elapsed": round(elapsed, 2),
            "nodes": len(snap_nodes), "snap_ok": snap_ok, "snap_error": snap_error,
            "avg_chars": avg_chars, "low_count": low_count, "node_stats": node_stats,
        })
        flag = "PASS" if (done and snap_ok and not getattr(task, "error", None)) else "FAIL"
        print(f"[{run_tag}] {flag} status={status_value} elapsed={elapsed:.2f}s "
              f"nodes={len(snap_nodes)} snapshot_ok={snap_ok} avg_chars={avg_chars} "
              f"低充实节点={low_count}")
        if snap_error:
            print(f"[{run_tag}]   快照问题: {snap_error}")
        if getattr(task, "error", None):
            print(f"[{run_tag}]   task.error: {task.error}")

    # ---- 明细统计表 ----
    print("=" * 64)
    print("内容充实度明细（script + segments 总字数，阈值 %d 字）" % CONTENT_MIN_CHARS)
    print("-" * 64)
    for rec in records:
        print(f"{rec['run']}  gen_id={rec['gen_id']}  avg={rec['avg_chars']}字  "
              f"不足节点数={rec['low_count']}/{rec['nodes']}")
        for s in rec["node_stats"]:
            mark = "内容不足" if s["low"] else "ok"
            print(f"    {s['node_id']:<12} {s['title']:<20} {s['chars']:>5}字  [{mark}]")

    # ---- 汇总断言 ----
    print("=" * 64)
    n = len(records)
    print(f"任务状态 done: {status_pass}/{n}")
    print(f"未捕获异常次数: {uncaught}")
    print(f"快照落盘合法: {sum(1 for r in records if r['snap_ok'])}/{n}")

    clean_note = ""
    if args.clean:
        removed = 0
        for d in created_gen_dirs:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        clean_note = f"（--clean 已删除 {removed} 个测试快照目录）"
    else:
        kept = [str(d) for d in created_gen_dirs if d.exists()]
        if kept:
            print("测试数据保留路径（可用 --clean 清理）:")
            for k in kept:
                print(f"  {k}")

    all_pass = (
        status_pass == n
        and uncaught == 0
        and all(r["snap_ok"] for r in records)
        and n == args.runs
    )
    print("-" * 64)
    if all_pass:
        print(f"结果: PASS  {n}/{n} 任务 done、无未捕获异常、快照 JSON 全部落盘合法 {clean_note}")
        if args.mode == "mock":
            print("说明: mock 模式下讲稿走本地兜底模板，字数偏少属预期；")
            print("      充实度统计用于校验统计链路，真实充实度请用 --mode llm 抽检。")
        return 0
    print(f"结果: FAIL  详见上方逐项输出 {clean_note}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
