"""嵌入通道健康检查（直连探测，绕开静默兜底）。

为什么需要这个脚本
------------------
`LLMClient.embed()` 在**任何异常**下都会静默返回全零向量
（ai_engine/core/llm.py:575-576），不抛错、不打日志。因此：

  - 灌库脚本报「成功写入 N 个 chunk」→ 其实写的是零向量
  - 检索报「最高分 1.0000」→ 那个 1.0 是 BM25 归一化的结果
    （ai_engine/rag/retrieve.py:400-408 除以最大值，每个通道第一名恒为 1.0）

结果是整个向量通道空转，而所有表面指标都是绿的。这个脚本直接调
embeddings 接口并把真实异常打出来，用来判定向量通道到底活没活。

用法
----
    # 1) 这家供应商到底提供哪些嵌入模型
    /d/anaconda/python scripts/verify_embedding.py --list-models

    # 2) 当前 .env 配的模型能不能用（打完整异常）
    /d/anaconda/python scripts/verify_embedding.py

    # 3) 逐个试探常见嵌入模型名，找出可用的（会发多次请求，按需使用）
    /d/anaconda/python scripts/verify_embedding.py --probe

退出码：0 = 向量通道正常；1 = 异常（含配置缺失、接口报错、返回零向量）。
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

# 中文输出防乱码（Windows 控制台默认 GBK）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# 允许直接 `python scripts/verify_embedding.py` 运行
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 常见的 OpenAI 兼容嵌入模型名，供 --probe 逐个试探
_CANDIDATE_MODELS = [
    "text-embedding-v3",
    "text-embedding-v2",
    "text-embedding-v1",
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
    "bge-m3",
    "bge-large-zh-v1.5",
    "m3e-base",
    "doubao-embedding",
    "embedding-3",
    "jina-embeddings-v3",
]

_PROBE_TEXT = "排序算法的时间复杂度"


def _mask(key: str) -> str:
    if not key:
        return "(空)"
    return f"{key[:8]}...{key[-4:]} (len={len(key)})"


def _describe(vec: list[float]) -> str:
    nonzero = sum(1 for x in vec if x != 0.0)
    norm = sum(x * x for x in vec) ** 0.5
    head = [round(x, 4) for x in vec[:5]]
    return f"dim={len(vec)} 非零分量={nonzero} L2范数={norm:.4f} head={head}"


def list_models(client) -> int:
    """列出供应商提供的模型，并标出疑似嵌入模型。"""
    print("=" * 68)
    print("GET {base_url}/models")
    try:
        page = client.models.list()
    except Exception:
        print("[FAIL] 拉取模型列表失败：")
        traceback.print_exc()
        return 1

    names = sorted(m.id for m in page.data)
    print(f"共 {len(names)} 个模型\n")
    for name in names:
        low = name.lower()
        marker = "  <-- 疑似嵌入模型" if any(
            kw in low for kw in ("embed", "bge", "m3e", "gte", "jina")
        ) else ""
        print(f"  {name}{marker}")

    if not any("embed" in n.lower() for n in names):
        print("\n[WARN] 列表里没有任何名字含 embed 的模型 ——")
        print("       这家供应商很可能不提供 embeddings 接口。")
    return 0


def probe(client, models: list[str]) -> int:
    """逐个试探候选模型名，报告哪些可用。"""
    print("=" * 68)
    print(f"逐个试探 {len(models)} 个候选嵌入模型（探测文本：{_PROBE_TEXT!r}）\n")
    usable: list[tuple[str, int]] = []
    for name in models:
        try:
            resp = client.embeddings.create(model=name, input=[_PROBE_TEXT])
            vec = list(resp.data[0].embedding)
            nonzero = any(x != 0.0 for x in vec)
            flag = "[OK]  " if nonzero else "[零向量]"
            print(f"  {flag} {name:<28} dim={len(vec)}")
            if nonzero:
                usable.append((name, len(vec)))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).replace("\n", " ")[:110]
            print(f"  [FAIL] {name:<28} {type(exc).__name__}: {msg}")

    print()
    if not usable:
        print("[FAIL] 没有一个候选模型可用 —— 需要换供应商或改用本地嵌入。")
        return 1
    print(f"[OK] 可用模型 {len(usable)} 个：")
    for name, dim in usable:
        print(f"  - {name}  (dim={dim})")
    print("\n把可用的那个写进 .env：")
    print(f"  AI_EMBEDDING_MODEL={usable[0][0]}")
    print(f"  AI_EMBEDDING_DIM={usable[0][1]}")
    if usable[0][1] != 1024:
        print(f"\n[注意] 维度是 {usable[0][1]}，不是 1024。pgvector 侧的列定义是")
        print("       halfvec(1024)（ai_engine/rag/store_pgvector.py 的 _ensure_tables），")
        print("       走持久化库时需要先改列定义或迁移。内存库不受影响。")
    return 0


def check_configured(client, embed_fn, model: str, dim: int) -> int:
    """探测当前 .env 配置的嵌入模型。"""
    print("=" * 68)
    print(f"直连探测（绕过 LLMClient.embed 的静默兜底）：model={model!r}")
    try:
        resp = client.embeddings.create(model=model, input=[_PROBE_TEXT])
    except Exception:
        print("\n[FAIL] 嵌入接口调用抛异常 —— 这就是被静默吞掉的那个错误：\n")
        traceback.print_exc()
        print("\n[结论] 向量通道不可用，灌进去的所有 chunk 都是零向量。")
        print("       下一步：跑 --list-models 看这家供应商到底有哪些嵌入模型，")
        print("       或跑 --probe 逐个试探候选模型名。")
        return 1

    if not getattr(resp, "data", None):
        print("[FAIL] 接口返回成功但 data 为空。")
        return 1

    vec = list(resp.data[0].embedding)
    print(f"\n接口返回：{_describe(vec)}")

    if not any(x != 0.0 for x in vec):
        print("[FAIL] 接口真的返回了全零向量（不是异常，是模型/服务端问题）。")
        return 1

    if len(vec) != dim:
        print(f"[WARN] 实际维度 {len(vec)} != .env 的 AI_EMBEDDING_DIM={dim}。")
        print("       内存库不受影响（存的是原始向量），但零向量兜底会用错维度，")
        print("       pgvector 的 halfvec(1024) 列也会插不进去。建议改成实际维度。")

    # 对照：走生产路径再调一次，确认静默兜底没有掩盖问题
    print("\n对照 —— 走生产路径 LLMClient.embed()：")
    via_client = embed_fn([_PROBE_TEXT])[0]
    if any(x != 0.0 for x in via_client):
        print(f"  [OK] {_describe(via_client)}")
        print("\n[PASS] 向量通道正常，可以重新灌库。")
        return 0
    print(f"  [FAIL] 返回零向量（{_describe(via_client)}）——")
    print("         直连能成功但生产路径失败，说明 EmbeddingService / LLMClient")
    print("         层还有别的配置问题（如 api_key、base_url 解析不同）。")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--list-models", action="store_true", help="列出供应商的全部模型")
    parser.add_argument("--probe", action="store_true", help="逐个试探候选嵌入模型名")
    parser.add_argument("--model", default="", help="覆盖要探测的嵌入模型名")
    args = parser.parse_args()

    from ai_engine.core import settings
    from ai_engine.core.llm import LLMClient, resolve_llm_base_url

    client = LLMClient()
    base_url = client.base_url
    model = args.model or settings.EMBEDDING_MODEL
    dim = settings.EMBEDDING_DIM

    print("=" * 68)
    print("嵌入通道配置")
    print("=" * 68)
    print(f"  AI_BASE_URL        = {base_url}")
    print(f"  AI_API_KEY         = {_mask(client.api_key)}")
    print(f"  AI_EMBEDDING_MODEL = {settings.EMBEDDING_MODEL}")
    print(f"  AI_EMBEDDING_DIM   = {dim}")
    print(f"  AI_GEN_MODE        = {settings.GEN_MODE}  (is_mock={settings.is_mock})")
    resolved, reason = resolve_llm_base_url(client.model)
    print(f"  resolved base_url  = {resolved}" + (f"  [{reason}]" if reason else ""))
    print()

    if settings.is_mock:
        print("[FAIL] 当前是 mock 模式，embed() 直接返回零向量，根本不会调接口。")
        print("       先设 AI_GEN_MODE=llm 再跑本脚本。")
        return 1
    if not client.api_key:
        print("[FAIL] AI_API_KEY 为空，embed() 直接返回零向量。")
        return 1

    from openai import OpenAI

    raw = OpenAI(api_key=client.api_key, base_url=base_url, timeout=client.timeout)

    if args.list_models:
        return list_models(raw)
    if args.probe:
        return probe(raw, _CANDIDATE_MODELS)
    return check_configured(raw, client.embed, model, dim)


if __name__ == "__main__":
    raise SystemExit(main())
