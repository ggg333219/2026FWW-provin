---
name: skill-checker
description: "Use this skill when the user wants to check, review, or evaluate a skill. Performs quality assessment across five dimensions (描述质量, 清晰度, 可执行性, 准确性, 完整性), generates quality tags and a quality report, and produces a structured eval JSON file at $AILY_WORKDIR/{skill_name}_eval.json."
---

# Skill Checker

对 skill 进行全维度质量审查，产出结构化评估文件。

## 产出格式

```json
{
  "tags": [{"label": "步骤清晰", "type": "positive"}, ...],
  "dimension_scores": [{"dimension": "描述质量", "score": 7.2}, ...],
  "report_content": "## 总体结论\n...",
  "created_at": 1757319000000
}
```

## 流程

### 1. 定位 skill 并读取内容

读取 SKILL.md，检查 frontmatter 中 `name` 和 `description` 是否存在且非空。

### 2. 全维度审查（0-10分）

| 维度 | 审查要点 |
|------|----------|
| **描述质量** | description 是否准确传达用途和触发场景；长度 100-200 词；祈使句式 |
| **清晰度** | 步骤有序编号、逻辑连贯、无歧义；输入/输出约定明确 |
| **可执行性** | 工具/命令是否可用；依赖的 SDK 是否已集成；脚本和资源文件是否齐全 |
| **准确性** | 命令语法正确；工具名和参数与实际一致；文件路径存在 |
| **完整性** | 覆盖完整工作流；有错误处理和边界条件；必要的资源文件齐全 |

### 3. 标签生成

- `positive` — 值得肯定的优点
- `warning` — 需要注意但不阻塞的问题
- `negative` — 明确的缺陷或风险

### 4. 质量检测报告

必须包含章节：总体结论、主要优点、可改进点（按严重程度标注「建议」「推荐」「重要」）、后续建议。

### 5. 生成 eval JSON

```bash
python scripts/generate_eval.py --skill-id <skill_id> --skill-name <name> \
  --tag "步骤清晰:positive" --tag "依赖未集成工具:negative" \
  --score "描述质量:7.2" --score "清晰度:8.0" --score "可执行性:5.4" \
  --score "准确性:6.8" --score "完整性:4.2" \
  --report-file /tmp/eval_report.md
```

### 6. 优化（按需）

仅在用户要求优化时执行：提取改进项 → 复制到可写临时目录 → 逐项修复 → 对比分析。
