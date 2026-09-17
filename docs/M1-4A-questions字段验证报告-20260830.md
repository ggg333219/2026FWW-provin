# M1-4A · questions 字段全链路验证报告

- 日期：2026-08-30
- 负责人：成员1（管逸恬）· 数据层标准化与节点修复
- 性质：只审计与写脚本，未修改任何生产代码
- 验证脚本：`scripts/verify_questions_field.py`（已运行，见第 4 节）

---

## 1. 验证目的

此前修过 questions 类型不统一的 bug（`TeachingNode.questions` 应为 `list[str]`，不能是 `list[dict]`，当时的修复落在 `ai_engine/gen/migrate_snapshot.py` 的旧快照迁移）。本次验证的目标是确认：**normalize 写入点这一层**是否也会把脏数据（`list[dict]`、`str`、`dict` 等）拦截并归一为 `list[str]`，即全链路上是否仍存在脏类型注入口。

## 2. 验证方法

1. `grep` 全 `ai_engine/` 目录，找出所有对 `questions` / `interactive_questions` 的写入点（append、赋值），逐一阅读上下文确认写入类型。
2. 以 import 链路确认生效的 normalize 写入点（排除未生效的旧代码）：
   - `ai_engine/schema.py::normalize_stage2_nodes`（被 `gen/outline.py`、`generator.py` 调用）
   - `ai_engine/schema.py::normalize_stage3_scripts`（被 `gen/node.py::NodeGenerator.generate_all` 调用）
   - `ai_engine/gen/node.py::NodeGenerator._normalize_enhanced_scripts`（被 `generate_enhanced` 调用）
   - 说明：`ai_engine/core/schema.py` 只是 pydantic 数据模型（`TeachingNode.questions: list[str]`），不含 normalize 函数；真正的 normalize 函数都在 `ai_engine/schema.py`。
3. 离线脚本构造 6 个样例节点（正常 / 缺字段 / `list[dict]` / str / None），跑 3 个写入点 × 6 样例 = 18 条断言，检查输出 `questions` 与 `interactive_questions` 是否均为 `list[str]` 且不崩溃。

## 3. 写入点清单

| # | 位置 | 写入方式 | 写入类型是否安全 |
|---|------|---------|----------------|
| 1 | `ai_engine/schema.py:231-232`（normalize_stage2_nodes） | `item.get("questions") or item.get("interactive_questions") or []` | **否** — 原样透传，无元素级 str 归一 |
| 2 | `ai_engine/schema.py:280-281`（normalize_stage3_scripts） | 同上 | **否** — 同上 |
| 3 | `ai_engine/gen/node.py:296-297`（_normalize_enhanced_scripts） | 同上 | **否** — 同上 |
| 4 | `ai_engine/generator.py:416`（LessonGenerator LLM 路径） | `data.get("interactive_questions") or fallback[...]` | **否** — LLM 返回值未做类型归一（经 `build_node_script_schema` 透传） |
| 5 | `ai_engine/generator.py:563-567`（LessonGenerator fallback） | 硬编码 3 条 f-string | 是 — `list[str]` |
| 6 | `ai_engine/gen/node.py:249`（_single_fallback） | 硬编码 1 条 f-string | 是 — `list[str]` |
| 7 | `ai_engine/gen/patch.py:151,164`（NodePatcher 新增节点） | 写入空 `[]` | 是 |
| 8 | `ai_engine/gen/interactive.py:48-54`（InteractiveBuilder.build_quiz LLM 路径） | `result.get("questions", [])` | **否（边界风险）** — LLM 路径产出 `list[dict{question,options,answer,explanation}]`；当前该结果只经 `/gen/interactive` 接口独立返回、不直接写入 `node.questions`，但若前端/后端把它回填进节点，就会复现 dict 类型污染 |
| 9 | `ai_engine/gen/interactive.py:104`（_fallback_quiz） | 硬编码 `list[dict]`（quiz 结构化题目） | 同上，属 quiz 物料的合法结构，非节点字段 |
| 10 | `ai_engine/gen/migrate_snapshot.py:56-84`（旧快照迁移） | `_normalize_questions()` dict→str 转换 | 是 — 这正是此前 bug 的修复点，只覆盖快照加载路径 |
| 11 | `ai_engine/core/schema.py:361,388` | pydantic `list[str]` 字段声明 | 模型层兜底：构造 TeachingNode 时 `list[dict]` 会触发 ValidationError（报错而非静默污染），这正是 migrate_snapshot 存在的原因 |

**结论**：三个生效的 normalize 写入点（#1/#2/#3）都只做"取值 + `or []`"的空值兜底，**没有任何元素级 str 归一**。dict→str 的拦截目前只存在于旧快照迁移（#10）一处。

## 4. 脚本运行结果

命令：`python scripts/verify_questions_field.py`（需先 `export PYTHONIOENCODING=utf-8`）

```text
汇总: 9/18 PASS, 9 FAIL
整体结论: FAIL
```

逐条结果（3 写入点 × 6 样例，三个写入点结果完全一致）：

| 样例 | 结果 |
|------|------|
| S1 正常节点（questions 为 list[str]） | PASS ×3 |
| S2 缺 questions 字段 | PASS ×3（兜底 `[]`） |
| S3 questions 为 `list[dict{question,answer,type}]` | **FAIL ×3** — dict 原样透传 |
| S4 无 questions、interactive_questions 为 `list[dict]` | **FAIL ×3** — dict 原样透传并双向扩散到 questions |
| S5 questions 为 str 脏数据 | **FAIL ×3** — str 原样透传（`or` 短路，非空字符串为真值） |
| S6 questions/interactive_questions 均为 None | PASS ×3（兜底 `[]`） |

全部 18 条用例均**未崩溃**（无异常抛出），但 9 条类型断言失败。

## 5. 结论

1. **正常路径安全，脏数据路径未拦截**：LLM/历史数据若输出 `list[dict]` 或 `str` 形态的 questions，三个 normalize 写入点都会原样放行到节点/快照；这些脏数据只有在快照**再次加载并经 migrate_snapshot 迁移**时才会被纠正，或被 pydantic `TeachingNode` 构造时以 ValidationError 的形式报错。
2. **此前 bug 的修复不完整**：修复只覆盖了 `migrate_snapshot.py`（存量快照迁移），未覆盖 normalize 写入点（增量防线缺失）。
3. **无崩溃风险**：透传本身不会抛异常，风险表现为下游类型污染（前端 `_slide_quiz` 期望字符串列表、`export_ppt.py:297` / `export_doc.py:138` / `validator.py:245` / `preview.py:171` 直接迭代 questions，遇到 dict 元素会按对象渲染或产出非预期输出）。
4. **修复建议**（不在本次范围内实施）：在 `normalize_stage2_nodes` / `normalize_stage3_scripts` / `_normalize_enhanced_scripts` 三处统一复用 `migrate_snapshot._normalize_questions()` 的归一逻辑（list 过滤出 str、dict 提取 `question/content/text` 键、str 包装为单元素列表、其余丢弃），即可在生成源头拦截脏类型。
