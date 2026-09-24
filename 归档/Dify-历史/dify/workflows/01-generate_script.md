# Workflow 1/7：generate_script（页级讲稿生成）

> 对应后端：`DifyClient.GenerateScript`  
> scene 值：`generate_script`  
> 接口：`POST /v1/workflows/run`

---

## 一、在 Dify 创建 Workflow 应用

1. 工作台 → **创建应用** → 选择 **工作流（Workflow）**
2. 名称：`智课-讲稿生成`
3. 创建后进入编排画布

---

## 二、开始节点：添加输入变量

| 变量名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `scene` | 文本 | 否 | 后端固定传 `generate_script` |
| `page` | 数字 | 是 | 页码 |
| `content` | 文本 | 是 | 课件该页内容 |
| `course_name` | 文本 | 否 | 课程名称 |
| `mode` | 文本 | 否 | 模式，通常 `llm` |

---

## 三、添加 LLM 节点

**模型：** 选你已配好的 `qwen-plus` 或 `qwen-turbo`

**Prompt：**

```text
你是高校课程讲稿撰写助手。请根据课件内容，生成适合口述的教学讲稿。

课程名称：{{course_name}}
页码：{{page}}

课件内容：
{{content}}

要求：
1. 语气自然，像老师在课堂上讲解
2. 结构清晰，150-400字
3. 同时给出该页知识点的思维导图 Markdown（用 # 和 - 列表）
4. 只输出 JSON，不要其他文字

输出格式：
{
  "page": {{page}},
  "script": "讲稿正文...",
  "mindmap_markdown": "# 标题\n- 要点1\n- 要点2"
}
```

---

## 四、添加「结束」节点

**输出变量名必须是 `result`**（后端从这个字段读取 JSON）。

- 如果 LLM 直接输出 JSON 字符串 → 结束节点 `result` = LLM 输出
- 如果 LLM 输出不稳定 → 中间加 **代码节点** 清洗 JSON，再传给 `result`

**代码节点示例（Python）：**

```python
import json
import re

def main(llm_text: str) -> dict:
    text = llm_text.strip()
    # 去掉 markdown 代码块包裹
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    data = json.loads(text)
    return {"result": json.dumps(data, ensure_ascii=False)}
```

结束节点输出：

| 变量 | 值 |
|------|-----|
| `result` | 代码节点的 `result` 或 LLM 的 JSON 字符串 |

---

## 五、发布并获取 Workflow API Key

1. 右上角 **发布**
2. 左侧 **访问 API** → **创建 API Key**
3. 复制 `app-xxx` Key

---

## 六、配置项目 .env

```env
# 已有：Chat 问答 Key
APP_AI_DIFY_API_KEY=app-你的ChatKey

# 新增：Workflow Key（本应用）
APP_AI_DIFY_WORKFLOW_API_KEY=app-你的WorkflowKey
```

---

## 七、本地验证（PowerShell）

```powershell
curl -X POST "http://127.0.0.1:18001/v1/workflows/run" `
  -H "Authorization: Bearer app-你的WorkflowKey" `
  -H "Content-Type: application/json" `
  -d "{\"inputs\":{\"scene\":\"generate_script\",\"page\":1,\"content\":\"机器学习是人工智能的一个分支...\",\"course_name\":\"AI导论\",\"mode\":\"llm\"},\"response_mode\":\"blocking\",\"user\":\"test\"}"
```

成功时 `data.outputs.result` 应包含：

```json
{"page":1,"script":"...","mindmap_markdown":"# ..."}
```

---

## 八、Go 后端验证

```powershell
cd backend
$env:APP_AI_DIFY_WORKFLOW_API_KEY="app-你的WorkflowKey"
go test ./internal/service/ -run TestGenerateScript -v
```

或重启后端后调用教师端讲稿生成接口。

---

## 九、完成标志

- [ ] Dify Workflow 应用已发布
- [ ] Workflow API Key 已填入 `.env`
- [ ] curl 测试返回合法 JSON
- [ ] 后端 `GenerateScript` 不再走 Python 降级

完成后继续：**03-generate_from_markdown.md**（下一个）
