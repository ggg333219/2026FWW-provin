"""M4-4 离线验证脚本：LLM 超时保护与重试逻辑（不联网、不消耗额度）

验证目标（对应 ai_engine/core/llm.py 的 LLMClient 加固）：
  1. 超时被捕获，不炸进程，最终返回 fallback 内容（used_fallback=True）
  2. 超时/连接类异常触发自动重试，且重试次数正确（最多 1 次，退避 2s→4s）
  3. 非重试类业务错误（如 429 限流）不盲目重试，直接走兜底
  4. chat_json 在超时场景下返回带 error 键的 dict，不抛异常
  5. 超时值可通过 LLM_TIMEOUT_SECONDS 环境变量配置，显式传入优先

实现方式：
  - monkeypatch LLMClient._post_chat_completions（真正的 OpenAI HTTP 出口），
    替换为抛 TimeoutError / 返回假响应的桩函数，全程无真实网络调用；
  - monkeypatch llm 模块的 time.sleep，记录退避间隔并跳过真实等待；
  - 进程内设置 AI_GEN_MODE=llm + 假 API key，确保走到真实调用分支。

运行：python scripts/verify_llm_timeout.py
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 必须在导入 ai_engine 之前设置：强制走真实调用分支（出口已被 monkeypatch，不联网）
os.environ["AI_GEN_MODE"] = "llm"
os.environ.setdefault("AI_API_KEY", "offline-verify-key")
os.environ.setdefault("LLM_TIMEOUT_SECONDS", "120")

from ai_engine.core import llm as llm_mod  # noqa: E402
from ai_engine.core.llm import LLMClient, resolve_llm_timeout  # noqa: E402

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


def fake_success_response(content='{"ok": true}'):
    """伪造 OpenAI chat.completions 成功响应结构。"""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=None,
    )


class Scenario:
    """按调用顺序消费预设行为（异常 → 抛出；否则作为返回值）。"""

    def __init__(self, behaviors):
        self.behaviors = list(behaviors)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        item = self.behaviors.pop(0) if self.behaviors else self.behaviors
        if isinstance(item, BaseException):
            raise item
        return item


def run_with_patches(behaviors, method, *args, **kwargs):
    """在 monkeypatch 下执行一次 LLMClient 方法，返回 (result, calls, sleeps)。"""
    scenario = Scenario(behaviors)
    calls = {"n": 0}

    def fake_post(self, messages, actual_model, actual_temperature, **kw):
        calls["n"] += 1
        return scenario(messages, actual_model, actual_temperature, **kw)

    sleeps = []
    original_post = LLMClient._post_chat_completions
    original_time = llm_mod.time
    LLMClient._post_chat_completions = fake_post
    llm_mod.time = SimpleNamespace(sleep=sleeps.append)
    try:
        client = LLMClient()
        result = getattr(client, method)(*args, **kwargs)
    finally:
        LLMClient._post_chat_completions = original_post
        llm_mod.time = original_time
    return result, calls["n"], sleeps


def main():
    print("=" * 64)
    print("verify_llm_timeout — LLM 超时保护离线验证（无真实网络调用）")
    print("=" * 64)

    # ---- 场景 1：持续超时 → 捕获不炸进程 + 重试 1 次（退避 2s）+ 返回 fallback ----
    result, calls, sleeps = run_with_patches(
        [TimeoutError("fake: request timed out"), TimeoutError("fake: request timed out")],
        "chat", "系统提示", "用户消息",
    )
    check("S1 超时不炸进程，返回 LLMResponse", isinstance(result, llm_mod.LLMResponse))
    check("S1 超时标记 used_fallback=True", result.used_fallback is True)
    check("S1 fallback 内容可用", "AI 服务暂时不可用" in result.content)
    check("S1 重试发生且次数正确（首调+1次重试=2）", calls == 2, f"calls={calls}")
    check("S1 指数退避为 2s", sleeps == [2.0], f"sleeps={sleeps}")
    check("S1 fallback_reason 记录超时", "fake: request timed out" in (result.fallback_reason or ""))

    # ---- 场景 2：第一次超时、重试成功 → 返回正常内容，不进 fallback ----
    result, calls, sleeps = run_with_patches(
        [TimeoutError("fake: request timed out"), fake_success_response('{"ok": true}')],
        "chat", "系统提示", "用户消息",
    )
    check("S2 重试后成功返回内容", result.content == '{"ok": true}')
    check("S2 成功结果 used_fallback=False", result.used_fallback is False)
    check("S2 调用次数=2（重试生效）", calls == 2, f"calls={calls}")
    check("S2 退避 2s 后重试", sleeps == [2.0], f"sleeps={sleeps}")

    # ---- 场景 3：业务错误（429 限流）不盲目重试 ----
    result, calls, sleeps = run_with_patches(
        [Exception("Error code: 429 - rate limit exceeded, please retry after 60s")],
        "chat", "系统提示", "用户消息",
    )
    check("S3 429 不触发重试（仅 1 次调用）", calls == 1, f"calls={calls}")
    check("S3 429 无退避等待", sleeps == [], f"sleeps={sleeps}")
    check("S3 429 走兜底返回", result.used_fallback is True)

    # ---- 场景 4：chat_json 端到端超时 → 返回带 error 键的 dict，不抛异常 ----
    result, calls, sleeps = run_with_patches(
        [TimeoutError("fake: request timed out"), TimeoutError("fake: request timed out")],
        "chat_json", "系统提示", "用户消息",
    )
    check("S4 chat_json 超时返回 dict 不抛异常", isinstance(result, dict))
    check("S4 chat_json 返回带 error 标记", "error" in result, f"keys={list(result.keys())}")
    check("S4 chat_json 底层仍重试 1 次", calls == 2, f"calls={calls}")

    # ---- 场景 5：超时值可配置（LLM_TIMEOUT_SECONDS）----
    default_timeout = resolve_llm_timeout()
    check("S5 默认超时为 120s（或环境变量预设值）", default_timeout == int(os.environ["LLM_TIMEOUT_SECONDS"]),
          f"timeout={default_timeout}")

    old = os.environ.get("LLM_TIMEOUT_SECONDS")
    os.environ["LLM_TIMEOUT_SECONDS"] = "7"
    try:
        check("S5 环境变量 LLM_TIMEOUT_SECONDS=7 生效", resolve_llm_timeout() == 7)
        check("S5 LLMClient() 默认读取环境变量", LLMClient().timeout == 7)
        check("S5 显式传入 timeout=300 优先", LLMClient(timeout=300).timeout == 300)
    finally:
        if old is None:
            os.environ.pop("LLM_TIMEOUT_SECONDS", None)
        else:
            os.environ["LLM_TIMEOUT_SECONDS"] = old

    # ---- 汇总 ----
    print("-" * 64)
    total = len(PASS_RESULTS) + len(FAIL_RESULTS)
    print(f"结果: {len(PASS_RESULTS)}/{total} PASS")
    if FAIL_RESULTS:
        print("失败项:")
        for name, detail in FAIL_RESULTS:
            print(f"  - {name}  [{detail}]")
        return 1
    print("全部通过：超时被捕获不炸进程；重试次数与退避正确；429 不重试；最终返回 fallback/mock 内容。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
