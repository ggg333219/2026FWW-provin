# M1-4B · normalize 函数完整性（字段对称性）深度审计报告

- 日期：2026-08-30
- 负责人：成员1（管逸恬）· 数据层标准化与节点修复
- 性质：只审计与写脚本，未修改任何生产代码
- 验证脚本：`scripts/verify_normalize_symmetry.py`（已运行，48 条注入用例，见第 3 节）

---

## 1. 审计对象与生效链路确认

| 函数 | 生效文件 | 调用链 |
|------|---------|--------|
| `normalize_stage2_nodes`（下称 **A**） | `ai_engine/schema.py:201` | `gen/outline.py:19,104`（大纲构建）、`generator.py:41,51,674`（LessonGenerator） |
| `NodeGenerator._normalize_enhanced_scripts`（下称 **B**） | `ai_engine/gen/node.py:261` | `gen/node.py::generate_enhanced`（S3 增强讲稿，`/gen/nodes` enhanced 路径） |

补充说明（import 链路核验结论）：
- `ai_engine/main.py` 的模型类来自 `ai_engine.core.schema`（纯 pydantic 模型），**normalize 函数生效文件是 `ai_engine/schema.py`**，两份文件分工不同，不存在"哪份生效"的冲突。
- `generator.py:261` 另有一份 `LessonGenerator._normalize_enhanced_scripts` 旧副本，输出字段集更窄（仅 node_id/title/script/segments，无 questions/layout_hint 等），服务于 markdown 路径。本报告以题目要求的 B（gen/node.py 版）为准，旧副本字段不一致问题在第 5 节风险中提及。
- 主流程 `/api/v1/gen/create`（main.py:1157-1190）中合并方式为 `{**node}` 后仅覆盖 `script`/`segments`，因此大纲节点字段（summary 等）实际不丢；B 函数自身的字段缺口影响的是直接消费 B 输出的路径（如 generate_enhanced 的调用方）。

## 2. 字段映射对称表

逐字段对比 A 与 B 的输出行为：

| 字段 | A（normalize_stage2_nodes） | B（_normalize_enhanced_scripts） | 对称性结论 |
|------|---------------------------|--------------------------------|-----------|
| node_id | `str().strip()`；空则占位 `node_{idx:03d}`；重复 ID **整节点丢弃**（seen 去重） | `_resolve_script_node_id`：支持 `node_ids` 数组首元素回退；无效 ID → `sorted(valid)[0]` 强映射 | **不对称（策略差异）**：A 会因重复 ID 丢节点，B 永不丢节点且强制映射到合法 ID |
| title | 空 → `知识节点{idx}`；`str().strip()` | 空 → node_id；`str().strip()` | 不对称（兜底值不同，均安全） |
| summary | ✅ `str().strip()` 输出 | ❌ **不输出**（B 输出键集合中无 summary） | **不对称：B 丢字段** |
| source_span | ✅ `str().strip()` | ❌ 不输出 | **不对称：B 丢字段** |
| prerequisites | ✅ 归一为 `list[str]`（str 化 + 去空） | ❌ 不输出 | **不对称：B 丢字段** |
| node_type / type | `content` → **`slide`** 值映射；`str().strip()` | **原样透传**，`content` 保持 `content` | **不对称：值映射缺失**（实测：A 出 `slide`，B 出 `content`） |
| key_points | key_pts 优先否则 core_pts；但 **key_pts 本身无 isinstance(list) 检查** | 同 A（代码相同） | **对称但同缺**：非 list 真值（如 str）原样透传 |
| core_points | `isinstance(core_pts, list)` 检查 ✅，但 list 内元素不 str 化 | 同 A | 对称但同缺：`list[dict]`/`[123]` 原样透传 |
| questions / interactive_questions | `x or y or []` 空值兜底，**无元素级 str 归一** | 同 A | 对称但同缺（详见 M1-4A 报告） |
| segments | **原样透传**（不逐段归一，不校验元素是 dict） | 逐段归一：segment_id/text/`node_id`（含 node_ids 回退）/segment_type（默认 explanation）/estimated_seconds（`int(x or 30)`）/difficulty/interaction_hint/knowledge_card | **不对称（A 松 B 严）**；B 的 `int()` 对非数字字符串**会崩溃** |
| estimated_seconds | A 不处理（透传所在段） | `int((seg).get("estimated_seconds") or 30)` | 不对称细节：① `0` 被 `or 30` 误改为 30（实测）；② `"abc"` 抛 `ValueError`（实测崩溃）；③ `"30"`/`45.5` 可 lax 转换成功 |
| layout_hint / font_size_hint / text_alignment / slide_background | 原样透传（可为任意类型，含 None） | 同 A | 对称但同缺：int/list/dict 原样透传，无类型守卫 |
| script | ❌ 不输出（大纲阶段无讲稿，合理） | ✅ 空 script 时用 segments 拼接兜底 | 结构差异（职责不同，合理） |
| 旧版节点 title 缺失 | 兜底"知识节点{idx}" | 兜底 node_id | 见上 |

## 3. 注入测试结果（脚本运行原文汇总）

命令：`python scripts/verify_normalize_symmetry.py`（先 `export PYTHONIOENCODING=utf-8`）

```text
用例总数: 48；A 失败 15；B 失败 20；A/B 结果不一致（不对称）用例: 5
整体结论: FAIL（A 失败 15，B 失败 20）
```

关键失败明细：

| 类别 | 注入 | A 结果 | B 结果 |
|------|------|--------|--------|
| **B 崩溃** | `segments="seg_1"`（str 传成应为 list 的位置） | PASS（原样透传） | **FAIL — AttributeError: 'str' object has no attribute 'get'** |
| **B 崩溃** | `segments[0].estimated_seconds="abc"` | PASS（透传） | **FAIL — ValueError: invalid literal for int() with base 10: 'abc'** |
| **不对称 ×4** | prerequisites 注入 None/"n2"/[123,None]/{"0":"n2"} | PASS（归一为 list[str]） | FAIL（**输出缺失 prerequisites 字段**） |
| **不对称 ×1** | 同上 segments estimated_seconds="abc" | PASS | FAIL（崩溃） |
| A/B 同缺 | questions 注入 str / `list[dict]` / `[123,None]` / dict | FAIL ×4 | FAIL ×4 |
| A/B 同缺 | interactive_questions 注入 str / `list[dict]` | FAIL ×2 | FAIL ×2 |
| A/B 同缺 | key_points 注入 str / `list[dict]` / `[123]` | FAIL ×3 | FAIL ×3 |
| A/B 同缺 | core_points 注入 `list[dict]` | FAIL ×1 | FAIL ×1 |
| A/B 同缺 | layout_hint / text_alignment / slide_background 注入 int 或 list | FAIL ×5 | FAIL ×5 |

安全的部分：title/summary/script 的任意脏注入（None/123/list）两函数都成功归一为 str；node_type/type、layout 系字段 None 注入、segments None 注入均 PASS。

## 4. 发现的问题清单（含文件:行号）

| # | 严重度 | 位置 | 问题 |
|---|--------|------|------|
| P1 | **高（崩溃）** | `ai_engine/gen/node.py:275`（`estimated_seconds` 的 `int(x or 30)`） | LLM 返回非数字字符串（如 `"约45秒"`、`"abc"`）时抛 `ValueError`，导致**整个增强批次生成退入 except 降级路径**（node.py:88-94），所有节点退兜底，不是单节点失败 |
| P2 | **高（崩溃）** | `ai_engine/gen/node.py:269`（`for seg in (item or {}).get("segments") or []`） | LLM 把 segments 输出为 str 时抛 `AttributeError`，同样导致整批降级 |
| P3 | **高（不对称）** | `ai_engine/gen/node.py:284-309`（B 输出字典） | B 丢失 `summary` / `source_span` / `prerequisites` 三字段；A 有、B 无。直接消费 B 输出的路径拿不到这些字段 |
| P4 | **中（不对称）** | `ai_engine/gen/node.py:300-301` | B 无 `content→slide` 的 node_type 值映射（A 有，schema.py:227-228）。同一节点经 A 出 `slide`、经 B 出 `content`，下游按 node_type 区分渲染时行为不一致 |
| P5 | **中（同缺）** | `ai_engine/schema.py:225,231-232,280-281`；`ai_engine/gen/node.py:295,298-299` | `key_points`/`questions`/`interactive_questions` 只做 `or` 空值兜底：非 list 真值（str/dict）与 `list[dict]`/`[123]` 原样透传，与 M1-4A 结论一致 |
| P6 | **低（语义）** | `ai_engine/gen/node.py:275`（及 generator.py:263 同款） | `or 30` 把合法的 `0` 秒也改写为 30；且 `int(45.5)` 静默截断为 45，无范围钳制（prompt 约定 15-120） |
| P7 | **低（不对称）** | `ai_engine/schema.py:206-210` vs `node.py:_resolve_script_node_id` | 重复 node_id：A 整节点丢弃（数据丢失），B 强映射到 sorted 首个合法 ID（数据串位）。两者对"ID 冲突"的语义完全相反 |
| P8 | **低** | `ai_engine/schema.py:284-286`（A 的 segments 透传） | A 不校验 segments 元素是否为 dict、不清洗 segment_id/text；下游若直接消费 stage2 输出的 segments 可能拿到缺字段段。当前主流程会再经 B/normalize_stage3_scripts 归一，风险被掩盖 |
| P9 | **信息** | `ai_engine/generator.py:261-293` | LessonGenerator 旧版 `_normalize_enhanced_scripts` 与 B 同名但输出字段集更窄（无 node_type/type/questions/layout 系），是第三套不一致的归一实现 |

## 5. 修复建议（按优先级，不在本次实施）

1. **P1/P2（先行）**：B 中 `estimated_seconds` 改为安全转换（复用 `schema.py::_to_int`，非法值回退 30）；segments 循环前加 `if not isinstance(seg, dict): continue`。可同时把 B 的整批 except 降级改为"单节点 try"，缩小故障爆炸半径。
2. **P3**：B 输出补齐 `summary`（`str(x.get("summary") or "").strip()`）、`source_span`、`prerequisites`（复用 A 的归一逻辑），或在调用侧明确"脚本归一只补 script/segments"的契约并保证 merge 侧回填。
3. **P4**：B 增加 `raw_type == "content" → "slide"` 映射，与 A 对齐；或把该映射抽成共享函数供两处调用。
4. **P5**：`questions`/`interactive_questions`/`key_points` 统一接入 `migrate_snapshot._normalize_questions()` / `_to_string_list()` 的元素级归一（与 M1-4A 报告建议一致）。
5. **P7**：明确 node_id 冲突策略（建议统一为 B 的"映射 + 计数后缀重命名"，避免丢节点）。
6. **P9**：中期将 generator.py 的旧版归一函数改为复用 gen/node.py 版本，收敛为单一实现。

## 6. 遗留风险与未验证范围

- 本审计为**离线静态注入测试**，未跑真实 LLM 全链路；P1/P2 的触发概率取决于 LLM 输出偏离 schema 的频率（`chat_with_schema` 约束下应较少，但 `generate_enhanced` 在 LLM 异常降级时会对 fallback 数据再次归一，兜底数据本身是安全的）。
- `estimated_seconds` 的 `int("30")` 能 lax 成功说明 pydantic 之外的裸 `int()` 存在，但 `"约45秒"` 这类中文数字串必然崩溃——真实发生率需在 S3 联调日志中抽样确认（本轮未访问运行日志）。
- 三个 normalize 函数 + LessonGenerator 旧副本共四套归一实现的完全收敛，属于代码质量提升阶段（Phase 3）工作，建议单独立项。
