# Workflow 3/7：generate_from_markdown（Markdown 三阶段 Pipeline）

> 对应后端：`DifyClient.GenerateFromMarkdown`  
> scene 值：`generate_from_markdown`  
> Python 引擎：Stage1 理解 → Stage2 节点树 → Stage3 讲稿

---

## 在统一 Workflow 里加第 3 条分支

```
开始
  ↓
IF/ELSE（scene）
  ├─ generate_script        → 讲稿 LLM（已有）
  ├─ parse_knowledge        → 知识点 LLM（已有）
  └─ generate_from_markdown → 三阶段 Pipeline（本指南）
```

---

## 一、开始节点：新增变量

| 变量名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `markdown` | 段落/文本 | 选填 | 本分支必填（测试时填） |
| `course_name` | 文本 | 选填 | 已有，可复用 |
| `mode` | 文本 | 选填 | 通常 `llm` |

> 开始节点统一选填；在 **本分支内** 校验 `markdown` 不为空。

---

## 二、分支内推荐结构（三阶段，对齐 Python 引擎）

```
IF scene == generate_from_markdown
  ↓
LLM-1 理解 Markdown（key_points）
  ↓
LLM-2 构建节点树（node_tree）
  ↓
LLM-3 生成节点讲稿（scripts）
  ↓
代码节点 组装 result
  ↓
结束
```

---

## 三、LLM-1：Markdown 理解

**模型：** `qwen-plus` / `qwen-turbo`

**SYSTEM：**
```text
你是课程内容结构化助手。请理解 Markdown 课件并提炼要点。
```

**USER（变量插入）：**
```text
课程名称：{{course_name}}

Markdown 内容：
{{markdown}}
```

**结构化输出 Schema：**
```json
{
  "type": "object",
  "properties": {
    "normalized_markdown": { "type": "string" },
    "key_points": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "required": ["normalized_markdown", "key_points"]
}
```

---

## 四、LLM-2：节点树

**SYSTEM：**
```text
你是教学节点树构建助手。根据 Markdown 和要点，输出 nodes 数组。
node_id 必须稳定可读，如 node_001、node_002。
```

**USER：**
```text
课程名称：{{course_name}}

Markdown：
{{LLM-1.normalized_markdown}}

要点：
{{LLM-1.key_points}}
```

**结构化输出 Schema：**
```json
{
  "type": "object",
  "properties": {
    "nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "node_id": { "type": "string" },
          "title": { "type": "string" },
          "summary": { "type": "string" },
          "source_span": { "type": "string" },
          "prerequisites": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["node_id", "title", "summary", "source_span", "prerequisites"]
      }
    }
  },
  "required": ["nodes"]
}
```

---

## 五、LLM-3：节点讲稿

**SYSTEM：**
```text
你是高校讲稿生成助手。为每个节点生成可直接口述的 script，并拆分为 segments。
```

**USER：**
```text
课程名称：{{course_name}}

节点列表：
{{LLM-2.nodes}}

原始 Markdown：
{{LLM-1.normalized_markdown}}
```

**结构化输出 Schema：**
```json
{
  "type": "object",
  "properties": {
    "scripts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "node_id": { "type": "string" },
          "title": { "type": "string" },
          "script": { "type": "string" },
          "segments": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "segment_id": { "type": "string" },
                "text": { "type": "string" },
                "node_id": { "type": "string" }
              },
              "required": ["segment_id", "text", "node_id"]
            }
          }
        },
        "required": ["node_id", "title", "script", "segments"]
      }
    }
  },
  "required": ["scripts"]
}
```

---

## 六、代码节点：组装最终 result

**输入：** LLM-1 / LLM-2 / LLM-3 的输出 + `course_name` + 原始 `markdown`

```python
import json

def main(
    course_name: str,
    markdown: str,
    stage1: dict,
    stage2: dict,
    stage3: dict,
) -> dict:
    payload = {
        "course_name": course_name or "未命名课程",
        "source_markdown": stage1.get("normalized_markdown") or markdown,
        "key_points": stage1.get("key_points") or [],
        "node_tree": {"nodes": stage2.get("nodes") or []},
        "scripts": stage3.get("scripts") or [],
        "used_fallback": False,
    }
    return {"result": json.dumps(payload, ensure_ascii=False)}
```

**结束节点：** `result` = 代码节点输出

---

## 七、后端期望的完整 JSON 示例

```json
{
  "course_name": "AI导论",
  "source_markdown": "# 机器学习\n\n...",
  "key_points": ["监督学习", "无监督学习"],
  "node_tree": {
    "nodes": [
      {
        "node_id": "node_001",
        "title": "机器学习概述",
        "summary": "介绍机器学习基本定义",
        "source_span": "第一章",
        "prerequisites": []
      }
    ]
  },
  "scripts": [
    {
      "node_id": "node_001",
      "title": "机器学习概述",
      "script": "同学们好，今天我们学习机器学习的基本概念……",
      "segments": [
        {
          "segment_id": "seg_1",
          "text": "同学们好，今天我们学习机器学习的基本概念……",
          "node_id": "node_001"
        }
      ]
    }
  ],
  "used_fallback": false
}
```

---

## 八、Dify 内测试输入

| 字段 | 值 |
|------|-----|
| scene | `generate_from_markdown` |
| course_name | `AI导论` |
| mode | `llm` |
| markdown | 见下方示例 |

**测试 Markdown 示例：**
```markdown
# 机器学习基础

## 监督学习
用标注数据训练模型，如分类和回归。

## 无监督学习
从无标注数据中发现模式，如聚类。
```

成功标志：`node_tree.nodes` 至少 1 条，`scripts` 至少 1 条，且 `node_id` 能对上。

---

## 九、API 验证

```powershell
curl -X POST "http://127.0.0.1:18001/v1/workflows/run" `
  -H "Authorization: Bearer app-你的WorkflowKey" `
  -H "Content-Type: application/json" `
  -d "{\"inputs\":{\"scene\":\"generate_from_markdown\",\"course_name\":\"AI导论\",\"markdown\":\"# 机器学习\\n\\n## 监督学习\\n分类与回归。\",\"mode\":\"llm\"},\"response_mode\":\"blocking\",\"user\":\"test\"}"
```

> 若 60 秒无响应：Dify API 可能卡住，执行 `docker compose restart dify-api`

---

## 十、Go 后端验证

```powershell
cd backend
go run test_workflow_generate_from_markdown.go
```

---

## 十一、简化版（可选）

若三阶段链路太长，可先用 **单个 LLM** 直接输出完整 JSON（结构化输出 Schema 按第七节示例配置）。  
质量略低于三阶段，但配置更快；后续再拆成三阶段。

---

## 十二、完成标志

- [ ] IF/ELSE 新增 `generate_from_markdown` 分支
- [ ] 测试返回 `node_tree` + `scripts`
- [ ] `generate_script` / `parse_knowledge` 回归正常
- [ ] Go `GenerateFromMarkdown` 不再走 Python 降级

完成后继续：**04-generate_node_script.md**
