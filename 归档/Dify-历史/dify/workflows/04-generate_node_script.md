# Workflow 4/7：generate_node_script（讲授节点讲稿）

> 对应后端：`DifyClient.GenerateNodeScript`  
> scene 值：`generate_node_script`  
> 业务场景：教师端按 **TeachingNode** 批量生成互动讲稿、思维导图、追问与段落映射

---

## 在统一 Workflow 里加第 4 条分支

```
开始
  ↓
IF/ELSE（scene）
  ├─ generate_script          → 页级讲稿（已有）
  ├─ parse_knowledge          → 知识点树（已有）
  ├─ generate_from_markdown   → Markdown Pipeline（进行中）
  └─ generate_node_script     → 讲授节点讲稿（本指南）
```

---

## 一、开始节点：新增变量

| 变量名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `teaching_node` | 段落/文本 | 选填 | 本分支必填，**JSON 字符串** |
| `course_name` | 文本 | 选填 | 课程名称 |
| `mode` | 文本 | 选填 | 通常 `llm` |

> 后端传入的 `teaching_node` 示例（Go 会 `json.Marshal` 后作为字符串传入）：

```json
{
  "node_id": "p1_n1",
  "title": "监督学习",
  "summary": "用标注数据训练模型，完成分类与回归任务。",
  "core_points": ["需要标注样本", "常见任务有分类和回归"],
  "examples": ["垃圾邮件识别", "房价预测"],
  "common_confusions": ["监督学习不等于必须有深度学习"]
}
```

---

## 二、IF/ELSE 新增分支

| 条件 | 分支 |
|------|------|
| `scene` **是** `generate_node_script` | → 节点讲稿 LLM |
| 其他已有分支 | 保持不变 |

---

## 三、LLM 节点：讲授节点讲稿

**模型：** `qwen-plus`（不要用 coder 模型）

**SYSTEM：**
```text
你是高校课程智能讲授编排助手。根据讲授节点信息，生成适合互动式课堂的讲授内容。
输出必须严格符合 JSON Schema，不要输出多余文字。
```

**USER（用变量插入器）：**
```text
课程名称：{{course_name}}

讲授节点（JSON）：
{{teaching_node}}

要求：
1. script 要像真实教师课堂讲解，自然流畅，150-400字
2. mindmap_markdown 用 # 和 - 列表概括本节点
3. interactive_questions 给出 2-3 个课堂追问
4. reteach_script 用换角度重讲的口吻，80-150字
5. transition 承上启下过渡到下一节点，1-2句
6. structured_markdown 含标题、要点、示例、易错点
7. knowledge_nodes 至少 1 条，含 node_id/title/level/difficulty
8. script_segments 将 script 拆成 2-5 段，每段含 segment_id/text/node_ids
9. node_id 和 title 必须与输入 teaching_node 一致
```

**结构化输出 Schema：**

```json
{
  "type": "object",
  "properties": {
    "node_id": { "type": "string" },
    "title": { "type": "string" },
    "script": { "type": "string" },
    "mindmap_markdown": { "type": "string" },
    "interactive_questions": {
      "type": "array",
      "items": { "type": "string" }
    },
    "reteach_script": { "type": "string" },
    "transition": { "type": "string" },
    "structured_markdown": { "type": "string" },
    "knowledge_nodes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "node_id": { "type": "string" },
          "parent_id": { "type": "string" },
          "level": { "type": "integer" },
          "title": { "type": "string" },
          "tags": {
            "type": "array",
            "items": { "type": "string" }
          },
          "prerequisites": {
            "type": "array",
            "items": { "type": "string" }
          },
          "difficulty": { "type": "string" },
          "coverage_span": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["node_id", "title"]
      }
    },
    "script_segments": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "segment_id": { "type": "string" },
          "text": { "type": "string" },
          "node_ids": {
            "type": "array",
            "items": { "type": "string" }
          },
          "confidence": { "type": "number" },
          "manual_override": { "type": "boolean" }
        },
        "required": ["segment_id", "text", "node_ids"]
      }
    }
  },
  "required": [
    "node_id",
    "title",
    "script",
    "mindmap_markdown",
    "interactive_questions",
    "reteach_script",
    "transition"
  ]
}
```

---

## 四、结束节点（无需代码节点）

本分支 **不需要代码节点**，直接接结束即可（避免 sandbox 未启动导致失败）。

| 变量 | 值 |
|------|-----|
| `result` | LLM → **structured_output**（Object） |

若结束节点只能选 `text`，则选 **LLM → text**（structured 和 text 里通常都有 JSON）。

> 后端 `decodeWorkflowOutput` 支持 `result` 为 Object 或 JSON 字符串，两种均可。

---

## 五、后端期望的完整 JSON 示例

```json
{
  "node_id": "p1_n1",
  "title": "监督学习",
  "script": "同学们好，今天我们聚焦监督学习。它的核心思路是……",
  "mindmap_markdown": "# 监督学习\n- 标注数据\n- 分类\n- 回归",
  "interactive_questions": [
    "如果没有标注数据，还能做监督学习吗？",
    "分类和回归的本质区别是什么？"
  ],
  "reteach_script": "我们换个角度：把监督学习理解成……",
  "transition": "理解监督学习后，下一节我们看无监督学习。",
  "structured_markdown": "# 监督学习\n\n## 核心要点\n- 需要标注样本\n\n## 示例\n- 垃圾邮件识别",
  "knowledge_nodes": [
    {
      "node_id": "p1_n1",
      "parent_id": "",
      "level": 1,
      "title": "监督学习",
      "tags": ["core"],
      "prerequisites": [],
      "difficulty": "medium",
      "coverage_span": ["seg_1", "seg_2"]
    }
  ],
  "script_segments": [
    {
      "segment_id": "seg_1",
      "text": "同学们好，今天我们聚焦监督学习。",
      "node_ids": ["p1_n1"],
      "confidence": 0.9,
      "manual_override": false
    }
  ]
}
```

---

## 六、Dify 内测试输入

| 字段 | 值 |
|------|-----|
| scene | `generate_node_script` |
| course_name | `AI导论` |
| mode | `llm` |
| teaching_node | 见下方 |

**teaching_node 测试值（整段粘贴）：**
```json
{"node_id":"p1_n1","title":"监督学习","summary":"用标注数据训练模型，完成分类与回归。","core_points":["需要标注样本","分类与回归是典型任务"],"examples":["垃圾邮件识别","房价预测"],"common_confusions":["监督学习不等于深度学习"]}
```

成功标志：`script` 非空，`node_id` = `p1_n1`，`interactive_questions` 至少 1 条。

---

## 七、API 验证

```powershell
curl -X POST "http://127.0.0.1:18001/v1/workflows/run" `
  -H "Authorization: Bearer app-你的WorkflowKey" `
  -H "Content-Type: application/json" `
  -d "{\"inputs\":{\"scene\":\"generate_node_script\",\"course_name\":\"AI导论\",\"mode\":\"llm\",\"teaching_node\":\"{\\\"node_id\\\":\\\"p1_n1\\\",\\\"title\\\":\\\"监督学习\\\",\\\"summary\\\":\\\"用标注数据训练模型\\\",\\\"core_points\\\":[\\\"需要标注\\\"],\\\"examples\\\":[\\\"分类\\\"],\\\"common_confusions\\\":[\\\"易混淆\\\"]}\"},\"response_mode\":\"blocking\",\"user\":\"test\"}"
```

---

## 八、Go 后端验证

```powershell
cd backend
go run test_workflow_generate_node_script.go
```

---

## 九、业务链路说明

后端在 `generateAndStoreTeachingNodeScripts` 中，对每个 TeachingNode 调用本接口，并将返回写入：

| 返回字段 | 数据库字段 |
|----------|------------|
| `script` | `script_text` |
| `reteach_script` | `reteach_script` |
| `transition` | `transition_text` |
| `mindmap_markdown` | `mindmap_markdown` |
| `interactive_questions` | `interactive_questions` |
| `structured_markdown` | `structured_markdown` |
| `knowledge_nodes` | `knowledge_nodes_json` |
| `script_segments` | `script_segments_json` |

---

## 十、完成标志

- [ ] IF/ELSE 新增 `generate_node_script` 分支
- [ ] 测试返回完整 JSON（至少含 script / mindmap / questions）
- [ ] 已有分支（generate_script / parse_knowledge）回归正常
- [ ] Go `GenerateNodeScript` 不再走 Python 降级

完成后继续：**05-reconstruct_document.md**
