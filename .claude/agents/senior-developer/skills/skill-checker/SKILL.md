---
name: skill-checker
description: "Use this skill when the user wants to check, review, or evaluate a skill. Performs quality assessment across five dimensions (描述质量, 清晰度, 可执行性, 准确性, 完整性), generates quality tags and a quality report covering strengths, improvements, and recommendations, and produces a structured eval JSON file at $AILY_WORKDIR/{skill_name}_eval.json."
---

# Skill Checker

对 skill 进行全维度质量审查，产出结构化评估文件 `$AILY_WORKDIR/{skill_name}_eval.json`。

## 产出文件格式

```json
{
  "tags": [{"label": "步骤清晰", "type": "positive"}, ...],
  "dimension_scores": [{"dimension": "描述质量", "score": 7.2}, ...],
  "report_content": "## 总体结论\n...",
  "created_at": 1757319000000
}
```

四个顶层字段全部必须。`created_at` 由脚本自动填充。

---

## 流程

判断用户在这个流程中的哪个位置，然后帮他往下推进。

### 1. 定位 skill 并读取内容

找到用户指定的 skill，读取其 SKILL.md。检查 frontmatter 中 `name` 和 `description` 是否存在且非空。

### 2. 全维度审查

逐维度分析，每个维度打 **0–10 分**：

| 维度 | 审查要点 |
|------|----------|
| **描述质量** | frontmatter `description` 是否准确传达用途和触发场景；是否有区分度；长度是否合适（100–200 词）；是否使用祈使句式 |
| **清晰度** | 步骤是否有序编号、逻辑连贯；指令是否无歧义；术语是否一致；输入/输出约定是否明确 |
| **可执行性** | 每个步骤引用的工具/命令是否可用；依赖的外部服务/SDK 是否已集成；脚本和资源文件是否齐全 |
| **准确性** | 命令语法是否正确；工具名和参数是否与实际一致；引用的文件路径是否存在；领域知识是否正确 |
| **完整性** | 是否覆盖完整工作流（从输入到输出）；是否有错误处理和边界条件；是否包含必要的资源文件 |

评分参考：
- **0–3**：严重不足，基本不可用
- **4–5**：有明显缺陷，需要较大改动
- **6–7**：基本可用，有改进空间
- **8–9**：质量良好，仅有小问题
- **10**：优秀，无可挑剔

### 3. 标签生成

基于审查结果打标签：

| type | 含义 |
|------|------|
| `positive` | 值得肯定的优点 |
| `warning` | 需要注意但不阻塞的问题 |
| `negative` | 明确的缺陷或风险 |

常见标签：有护栏机制、步骤清晰、有效果对比表、资源文件齐全、描述混乱、缺少示例、触发条件不可执行、步骤冗杂、仅单文件缺资源、依赖未集成工具

### 4. 质量检测报告

生成 markdown 格式报告，包含章节：

```markdown
## 总体结论

概括该 skill 的定位、核心价值和整体质量水平。

## 主要优点

逐项列出 skill 的亮点（来源：positive 标签、高分维度的审查记录）。

## 可改进点

逐项列出问题和改进建议，按严重程度标注「建议」「推荐」「重要」。

## 后续建议

2–3 条优先级排序的改进方向。
```

### 5. 生成 eval JSON

```bash
python scripts/generate_eval.py --skill-id <skill_id> --skill-name <name> \
  --tag "步骤清晰:positive" --tag "依赖未集成工具:negative" \
  --score "描述质量:7.2" --score "清晰度:8.0" --score "可执行性:5.4" \
  --score "准确性:6.8" --score "完整性:4.2" \
  --report-file /tmp/eval_report.md
```

### 6. 优化（按需）

仅在用户要求优化时执行：
1. 从 eval 结果提取需改进项，按优先级排序
2. 将 skill 目录复制到可写临时目录作为工作副本
3. 逐项修复：定位根因 → 提出方案 → 执行修改 → 单项验证
4. 对比分析：展示维度得分变化、标签变化
5. 优化后副本保留在临时目录，由用户决定是否替换原始 skill
