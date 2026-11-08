"""F01/F02 验收脚本 —— 走完整真实链路（浏览器同款路径）。

链路：HTTP → Go 网关(8082) → Python AI 引擎(8000) → OpenAI 兼容模型端点(8899)
模型端点是**受控桩**，用于稳定复现真实模型常见的格式偏差；
它证明的是"归一/合并/透传逻辑在真实链路上成立"，**不等于真实大模型已验证**。

验收标准来源：A12 项目答辩前团队执行方案 · 三、第一轮验收 · F01/F02 行
"""

import json
import urllib.request

URL = "http://127.0.0.1:8082/api/v1/intent/extract"

PASS, FAIL = "PASS", "FAIL"
results = []


def call(sid, teacher_text):
    body = json.dumps(
        {"session_id": sid, "messages": [{"role": "teacher", "content": teacher_text}]},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    raw = urllib.request.urlopen(req, timeout=90).read().decode("utf-8")
    d = json.loads(raw)
    return d.get("data", d)


def check(label, ok, detail=""):
    results.append((PASS if ok else FAIL, label, detail))
    print(f"  [{PASS if ok else FAIL}] {label}" + (f"  —— {detail}" if detail else ""))


def summary_of(data):
    return data.get("intent_summary", {}) or {}


# ---------------------------------------------------------------- 场景 1
print("\n[场景 1] 团队固定主样例（方案第八节）")
print("  输入: 请帮我做一节45分钟的冒泡排序与快速排序课件，面向大一计算机专业学生，教师要求包含互动选择题。")
FIXED = "请帮我做一节45分钟的冒泡排序与快速排序课件，面向大一计算机专业学生，教师要求包含互动选择题。"
d = call("acc_fixed_sample", FIXED)
s = summary_of(d)
print(f"  引擎={d.get('engine')}  used_fallback={d.get('used_fallback')}")
print(f"  归一说明={d.get('normalization_notes')}")
print(f"  知识点={s.get('knowledge_points')}  互动={s.get('with_interactive')}")

check("验收1: 已知 output_format 正确规范化 (PPT→ppt)",
      s.get("output_format") == ["ppt"], f"实际={s.get('output_format')}")
check("验收2: 核心知识点保留 冒泡排序/快速排序",
      s.get("knowledge_points") == ["冒泡排序", "快速排序"], f"实际={s.get('knowledge_points')}")
check("验收3: 互动练习不覆盖知识点",
      "互动选择题" not in (s.get("knowledge_points") or []) and s.get("with_interactive") is True,
      f"知识点={s.get('knowledge_points')} with_interactive={s.get('with_interactive')}")
check("验收4: 真实模型成功（非规则兜底）且有归一记录",
      d.get("used_fallback") is False and bool(d.get("normalization_notes")),
      f"used_fallback={d.get('used_fallback')} notes={d.get('normalization_notes')}")

# ---------------------------------------------------------------- 场景 2
print("\n[场景 2] 脏格式输出（字符串时长 / 字符串列表 / 未知格式 / 多余字段）")
d = call("acc_dirty_format", "触发脏格式C：请帮我做一节45分钟的冒泡排序与快速排序课件。")
s = summary_of(d)
print(f"  归一说明={d.get('normalization_notes')}")
check("时长 '45分钟' 归一为 45", s.get("duration_minutes") == 45, f"实际={s.get('duration_minutes')}")
check("字符串知识点 '冒泡排序、快速排序' 拆成列表",
      s.get("knowledge_points") == ["冒泡排序", "快速排序"], f"实际={s.get('knowledge_points')}")
check("未知格式 flash 被丢弃，PPT/Word 保留",
      s.get("output_format") == ["ppt", "doc"], f"实际={s.get('output_format')}")
check("多余字段 reasoning 被忽略并记录",
      any("reasoning" in n for n in (d.get("normalization_notes") or [])),
      f"notes={d.get('normalization_notes')}")

# ---------------------------------------------------------------- 场景 3
print("\n[场景 3] 模型脑补知识点（红黑树/教师从未提及）")
d = call("acc_hallucination", "触发脑补A：请帮我做一节45分钟的冒泡排序与快速排序课件。")
s = summary_of(d)
print(f"  知识点={s.get('knowledge_points')}")
check("脑补的 红黑树 被丢弃",
      "红黑树" not in (s.get("knowledge_points") or []), f"实际={s.get('knowledge_points')}")
check("教师说过的知识点仍在",
      "冒泡排序" in (s.get("knowledge_points") or []), f"实际={s.get('knowledge_points')}")

# ---------------------------------------------------------------- 场景 4
print("\n[场景 4] 真实模型失败 → 规则兜底，且有记录")
d = call("acc_model_failure", "触发失败B：请帮我做一节45分钟的冒泡排序与快速排序课件。")
s = summary_of(d)
print(f"  引擎={d.get('engine')}  used_fallback={d.get('used_fallback')}  reason={d.get('fallback_reason')}")
check("模型失败被标记为兜底", d.get("used_fallback") is True, f"used_fallback={d.get('used_fallback')}")
check("兜底原因有记录", bool(d.get("fallback_reason")), f"fallback_reason={d.get('fallback_reason')}")
check("兜底时切换到规则引擎", d.get("engine") == "IntentEngine", f"engine={d.get('engine')}")
check("兜底路径下知识点不被 '包含互动' 污染",
      "互动选择题" not in (s.get("knowledge_points") or []), f"实际={s.get('knowledge_points')}")

# ---------------------------------------------------------------- 汇总
print("\n" + "=" * 70)
p = sum(1 for r in results if r[0] == PASS)
f = sum(1 for r in results if r[0] == FAIL)
print(f"验收结果：{p} 通过 / {f} 不通过 / 共 {len(results)} 项")
if f:
    print("\n不通过项：")
    for r in results:
        if r[0] == FAIL:
            print(f"  - {r[1]}  {r[2]}")
raise SystemExit(1 if f else 0)
