# Workflow 2/7：parse_knowledge（知识点树解析）

> 对应后端：`DifyClient.ParseKnowledge`  
> scene 值：`parse_knowledge`  
> 业务接口：`POST /api/v1/ai/parse-knowledge`

---

## 方案选择

**推荐：在现有「智课-讲稿生成」Workflow 里加分支**（同一个 Workflow API Key，不用改 `.env`）

```
开始 → IF/ELSE（按 scene 分流）
         ├─ generate_script  → LLM讲稿 → 结束
         └─ parse_knowledge  → LLM知识点 → 结束
```

---

## 一、开始节点：补充输入变量

在原有变量基础上，确保有：

| 变量名 | 类型 | 用于 scene |
|--------|------|------------|
| `scene` | 文本 | 两个分支都用 |
| `text` | 文本 | parse_knowledge |
| `mode` | 文本 | parse_knowledge |
| `page` / `content` / `course_name` | 已有 | generate_script |

`text`、`mode` 设为**选填**（讲稿分支不用填）。

---

## 二、添加 IF/ELSE 节点（若还没有）

在「开始」和 LLM 之间插入 **条件分支**：

| 条件 | 分支 |
|------|------|
| `scene` **是** `parse_knowledge` | → 知识点 LLM |
| `scene` **是** `generate_script` | → 讲稿 LLM（已有） |
| ELSE | → 讲稿 LLM（兼容旧调用） |

---

## 三、知识点 LLM 节点

**模型：** `qwen-plus` 或 `qwen-turbo`（不要用 coder 模型）

**SYSTEM：**
```text
你是课程知识点结构化助手。将输入文本拆解为层级知识点树。
```

**USER（用变量插入器插入 text，不要手打）：**
```text
请将以下内容拆解为知识点树：

{{text}}
```

**结构化输出 Schema：**

```json
{
  "type": "object",
  "properties": {
    "structure": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "children": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "name": { "type": "string" },
                "children": { "type": "array" }
              },
              "required": ["name"]
            }
          }
        },
        "required": ["name"]
      }
    }
  },
  "required": ["structure"]
}
```

---

## 四、结束节点

知识点分支的结束节点输出：

| 变量 | 值 |
|------|-----|
| `result` | `structured_output` 转 JSON 字符串 |

若 `structured_output` 已是 `{ "structure": [...] }`，代码节点：

```python
import json

def main(structured_output: dict) -> dict:
    return {"result": json.dumps(structured_output, ensure_ascii=False)}
```

**后端期望的 result 内容：**

```json
{
  "structure": [
    {
      "name": "人工智能导论",
      "children": [
        { "name": "机器学习" },
        { "name": "深度学习" }
      ]
    }
  ]
}
```

---

## 五、Dify 内测试

测试运行输入：

| 字段 | 值 |
|------|-----|
| scene | `parse_knowledge` |
| text | `人工智能包括机器学习、深度学习、自然语言处理。机器学习分为监督学习和无监督学习。` |
| mode | `llm` |

成功标志：结果含 `structure` 数组，且至少 1 个节点有 `name`。

---

## 六、API 验证（60 秒内应返回，超时重启 dify-api）

```powershell
curl -X POST "http://127.0.0.1:18001/v1/workflows/run" `
  -H "Authorization: Bearer app-你的WorkflowKey" `
  -H "Content-Type: application/json" `
  -d "{\"inputs\":{\"scene\":\"parse_knowledge\",\"text\":\"人工智能包括机器学习、深度学习。\",\"mode\":\"llm\"},\"response_mode\":\"blocking\",\"user\":\"test\"}"
```

---

## 七、Go 后端验证

```powershell
cd backend
$env:APP_AI_DIFY_WORKFLOW_API_KEY="app-你的WorkflowKey"
go run test_workflow_parse_knowledge.go
```

---

## 八、业务接口验证（需后端运行）

```powershell
curl -X POST "http://127.0.0.1:18080/api/v1/ai/parse-knowledge" `
  -H "Content-Type: application/json" `
  -d "{\"fileContent\":\"人工智能包括机器学习、深度学习、自然语言处理。\",\"fileType\":\"text\",\"studentId\":\"test-student\"}"
```

---

## 九、完成标志

- [ ] IF/ELSE 按 scene 正确分流
- [ ] parse_knowledge 测试返回 structure
- [ ] generate_script 分支仍正常（回归测试）
- [ ] Go `ParseKnowledge` 不再走 Python 降级

完成后继续：**03-generate_from_markdown.md**
