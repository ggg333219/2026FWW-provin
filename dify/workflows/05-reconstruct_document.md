# Workflow 5/7：reconstruct_document（课件重构为讲授节点）

> 对应后端：`DifyClient.ReconstructDocument`  
> scene 值：`reconstruct_document`  
> 业务场景：教师上传课件 → 解析出 `parsed_pages` → **重构为章节 + TeachingNode 列表**

---

## 在统一 Workflow 里加第 5 条分支

```
开始
  ↓
IF/ELSE（scene）
  ├─ generate_script          → 已有
  ├─ parse_knowledge          → 已有
  ├─ generate_from_markdown   → 进行中
  ├─ generate_node_script     → 已有
  └─ reconstruct_document     → 本指南
```

---

## 一、开始节点：新增变量

| 变量名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `parsed_document` | 段落/文本 | 选填 | 本分支必填，**JSON 字符串** |
| `mode` | 文本 | 选填 | 后端通常传 `hybrid` 或 `llm` |

> 后端传入结构（Go `json.Marshal` 后作为字符串）：

```json
{
  "doc_id": "doc_abc123",
  "doc_name": "机器学习导论.pptx",
  "doc_type": "pptx",
  "total_pages": 2,
  "parsed_pages": [
    {
      "page": 1,
      "content": "第一章 机器学习概述\n- 机器学习是人工智能的分支\n- 监督学习与非监督学习",
      "content_length": 58
    },
    {
      "page": 2,
      "content": "第二章 监督学习\n- 分类与回归\n- 例如：垃圾邮件识别",
      "content_length": 42
    }
  ]
}
```

---

## 二、IF/ELSE 新增分支

| 条件 | 分支 |
|------|------|
| `scene` **是** `reconstruct_document` | → 重构 LLM |
| 其他已有分支 | 保持不变 |

---

## 三、LLM 节点：文档重构

**模型：** `qwen-plus`

**SYSTEM：**
```text
你是课程内容重构助手。请将页级解析文本重组为「章节 chapters」和「讲授节点 teaching_nodes」。
node_id 使用 node_001、node_002 格式；chapter_id 使用 chapter_001 格式。
必须保留输入中的 doc_id、doc_name、doc_type。
```

**USER（用变量插入器）：**
```text
模式：{{mode}}

解析文档（JSON）：
{{parsed_document}}

要求：
1. 每一页或每一主题块至少生成 1 个 teaching_node
2. 每个节点包含：title、summary、core_points、examples、common_confusions
3. source_pages 标注来源页码数组，如 [1]
4. recommended_explanation_order 给出 3-4 步讲解顺序
5. estimated_duration 估算秒数（45-120）
6. next_node_id 指向下一个节点 ID，最后一个可为空字符串
7. chapters 将 node_ids 分组，每章有 chapter_id 和 title
8. 只输出 JSON，符合 Schema
```

**结构化输出 Schema：**

```json
{
  "type": "object",
  "properties": {
    "doc_id": { "type": "string" },
    "doc_name": { "type": "string" },
    "doc_type": { "type": "string" },
    "chapters": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "chapter_id": { "type": "string" },
          "title": { "type": "string" },
          "node_ids": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["chapter_id", "title", "node_ids"]
      }
    },
    "teaching_nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "node_id": { "type": "string" },
          "title": { "type": "string" },
          "source_pages": {
            "type": "array",
            "items": { "type": "integer" }
          },
          "summary": { "type": "string" },
          "core_points": {
            "type": "array",
            "items": { "type": "string" }
          },
          "examples": {
            "type": "array",
            "items": { "type": "string" }
          },
          "common_confusions": {
            "type": "array",
            "items": { "type": "string" }
          },
          "recommended_explanation_order": {
            "type": "array",
            "items": { "type": "string" }
          },
          "estimated_duration": { "type": "integer" },
          "next_node_id": { "type": "string" }
        },
        "required": ["node_id", "title", "source_pages", "summary", "core_points"]
      }
    }
  },
  "required": ["doc_id", "doc_name", "doc_type", "chapters", "teaching_nodes"]
}
```

---

## 四、结束节点（无需代码节点）

| 变量 | 值 |
|------|-----|
| `result` | LLM → **structured_output**（或 **text**） |

---

## 五、后端期望的完整 JSON 示例

```json
{
  "doc_id": "doc_abc123",
  "doc_name": "机器学习导论.pptx",
  "doc_type": "pptx",
  "chapters": [
    {
      "chapter_id": "chapter_001",
      "title": "第一章 机器学习概述",
      "node_ids": ["node_001"]
    },
    {
      "chapter_id": "chapter_002",
      "title": "第二章 监督学习",
      "node_ids": ["node_002"]
    }
  ],
  "teaching_nodes": [
    {
      "node_id": "node_001",
      "title": "机器学习概述",
      "source_pages": [1],
      "summary": "介绍机器学习的基本定义与主要分支。",
      "core_points": ["机器学习是 AI 分支", "分为监督与非监督学习"],
      "examples": ["推荐系统"],
      "common_confusions": ["机器学习是否等于深度学习"],
      "recommended_explanation_order": ["开场点题", "解释核心概念", "总结"],
      "estimated_duration": 60,
      "next_node_id": "node_002"
    },
    {
      "node_id": "node_002",
      "title": "监督学习",
      "source_pages": [2],
      "summary": "讲解监督学习的分类与回归任务。",
      "core_points": ["分类", "回归"],
      "examples": ["垃圾邮件识别"],
      "common_confusions": ["分类和回归的区别"],
      "recommended_explanation_order": ["回顾上节", "讲解分类回归", "举例"],
      "estimated_duration": 75,
      "next_node_id": ""
    }
  ]
}
```

---

## 六、Dify 内测试输入

| 字段 | 值 |
|------|-----|
| scene | `reconstruct_document` |
| mode | `hybrid` |
| parsed_document | 见下方 |

**parsed_document 测试值（整段粘贴）：**
```json
{"doc_id":"doc_test_001","doc_name":"AI导论.pptx","doc_type":"pptx","total_pages":2,"parsed_pages":[{"page":1,"content":"第一章 机器学习概述\n- 机器学习是人工智能的分支\n- 监督学习与非监督学习","content_length":58},{"page":2,"content":"第二章 监督学习\n- 分类与回归\n- 例如：垃圾邮件识别","content_length":42}]}
```

成功标志：
- `teaching_nodes` 至少 2 条
- `chapters` 至少 1 条，且 `node_ids` 与节点对应
- `doc_id` = `doc_test_001`

---

## 七、API 验证

```powershell
curl -X POST "http://127.0.0.1:18001/v1/workflows/run" `
  -H "Authorization: Bearer app-你的WorkflowKey" `
  -H "Content-Type: application/json" `
  -d "{\"inputs\":{\"scene\":\"reconstruct_document\",\"mode\":\"hybrid\",\"parsed_document\":\"{\\\"doc_id\\\":\\\"doc_test_001\\\",\\\"doc_name\\\":\\\"AI导论.pptx\\\",\\\"doc_type\\\":\\\"pptx\\\",\\\"total_pages\\\":2,\\\"parsed_pages\\\":[{\\\"page\\\":1,\\\"content\\\":\\\"机器学习概述\\\"},{\\\"page\\\":2,\\\"content\\\":\\\"监督学习\\\"}]}\"},\"response_mode\":\"blocking\",\"user\":\"test\"}"
```

---

## 八、Go 后端验证

```powershell
cd backend
go run test_workflow_reconstruct_document.go
```

---

## 九、业务链路说明

课件上传流程（`courseService`）：

```
ParseDocument → 得到 parsed_pages
      ↓
ReconstructDocument（本接口）→ chapters + teaching_nodes
      ↓
saveTeachingNodes → 写入 teaching_nodes 表
      ↓
GenerateNodeScript（04）→ 为每个节点生成讲稿
```

后端调用时 `mode` 固定为 **`hybrid`**，Dify 分支可忽略或作为提示词参考。

---

## 十、完成标志

- [ ] IF/ELSE 新增 `reconstruct_document` 分支
- [ ] 测试返回 `chapters` + `teaching_nodes`
- [ ] 已有分支回归正常
- [ ] Go `ReconstructDocument` 不再走 Python 降级

完成后继续：**06-parse_document.md**
