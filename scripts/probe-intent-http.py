"""S1 意图接口探针 —— 打印一次请求的关键字段，用于快速核对结果来源。

用法：
    python scripts/probe-intent-http.py [端口]

默认端口 8082（Go 网关）。也可用 8000/8010/8020 直连 AI 引擎，
分别对应：真实模型路径 / mock 模式 / 模型不可达（规则兜底）。

关注字段：
    model_source       —— real_model / mock / rule_fallback / rule_engine
                          （本次新增，是判断"结果到底是谁算出来的"唯一依据）
    used_fallback      —— 是否降级到规则引擎
    degraded           —— used_fallback 的显式别名（Python 侧无条件输出）
    fallback_reason    —— 降级根因
    normalization_notes—— 模型输出的归一说明（非空 ⇔ 模型输出被采用）
"""

import json
import sys
import urllib.request

port = sys.argv[1] if len(sys.argv) > 1 else "8082"
url = f"http://127.0.0.1:{port}/api/v1/intent/extract"
body = json.dumps(
    {
        "session_id": f"probe-{port}-001",
        "messages": [
            {
                "role": "teacher",
                "content": "请帮我做一节45分钟的冒泡排序与快速排序课件，面向大一计算机专业学生，教师要求包含互动选择题。",
            }
        ],
    },
    ensure_ascii=False,
).encode("utf-8")
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
d = json.loads(urllib.request.urlopen(req, timeout=90).read().decode("utf-8"))
d = d.get("data", d)
s = d.get("intent_summary", {})
print(f"[port {port}] engine={d.get('engine')!r} used_fallback={d.get('used_fallback')!r} degraded={d.get('degraded')!r}")
print(f"[port {port}] fallback_reason={d.get('fallback_reason')!r} normalization_notes={d.get('normalization_notes')!r}")
print(f"[port {port}] model_source={d.get('model_source')!r}")
print(f"[port {port}] topic={s.get('topic')!r} duration={s.get('duration_minutes')!r} style={s.get('style')!r}")
print(f"[port {port}] knowledge_points={s.get('knowledge_points')!r} with_interactive={s.get('with_interactive')!r} output_format={s.get('output_format')!r}")
print(f"[port {port}] completion_pct={d.get('completion_pct')}")
