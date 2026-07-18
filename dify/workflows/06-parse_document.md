# Workflow 6/7：parse_document（课件文件解析）

> 对应后端：`DifyClient.ParseDocument`  
> scene 值：`parse_document`  
> 业务场景：教师上传 **PDF/PPTX** → 提取页级文本 → 供 `reconstruct_document`（05）使用

---

## 与前面几个功能的区别

| 项 | 说明 |
|----|------|
| 输入 | **文件**（不是纯文本 JSON） |
| 后端流程 | 先调 Dify `/v1/files/upload`，再调 workflow |
| Dify 节点 | 需要 **文档提取器** + LLM 结构化 |
| 页码精度 | 略低于 Python 引擎（PyMuPDF/python-pptx），但可演示闭环 |

> Go 后端已实现：上传文件 → 拿 `upload_file_id` → 传入 workflow 的 `file` 变量。

---

## 在统一 Workflow 里加第 6 条分支

```
开始（含 file 变量）
  ↓
IF/ELSE（scene）
  └─ parse_document
        ↓
     文档提取器（读 file）
        ↓
     LLM（结构化为 parsed_pages）
        ↓
     结束（result）
```

---

## 一、开始节点：新增变量

| 变量名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `file` | **单文件** | 选填 | 本分支必填，支持 PDF/PPTX |
| `filename` | 文本 | 选填 | 后端会传原始文件名，如 `AI导论.pptx` |
| `scene` | 文本 | 选填 | 后端固定传 `parse_document` |

> ⚠️ 变量名必须是 **`file`**（与 Go 后端一致，不能改成 document_file）。

其他已有变量（page、content、text 等）保持选填即可。

---

## 二、IF/ELSE 新增分支

| 条件 | 分支 |
|------|------|
| `scene` **是** `parse_document` | → 文档提取器 |
| 其他已有分支 | 保持不变 |

---

## 三、文档提取器节点

**输入：** 开始节点 → `file`

**说明：** 该节点从 PDF/PPTX 中提取纯文本，输出变量通常为 **`text`**（整份文档文本）。

---

## 四、LLM 节点：结构化为 parsed_pages

**模型：** `qwen-plus`

**SYSTEM：**
```text
你是文档解析结构化助手。将提取的课件文本按页/幻灯片拆分为 parsed_pages 数组。
只输出 JSON，符合 Schema。
```

**USER：**
```text
文件名：{{filename}}

提取的全文：
{{文档提取器 / text}}

要求：
1. doc_name 使用 filename；doc_type 根据后缀判断 pdf 或 pptx
2. doc_id 生成 doc_ 开头的随机 ID，如 doc_a1b2c3d4e5f6
3. 按页/幻灯片逻辑拆分，每页一条 parsed_pages
4. page 从 1 递增；content_length = content 字符数
5. total_pages = parsed_pages 条数（或文档总页数估计值）
6. 不要丢失各页要点 bullet
```

**结构化输出 Schema：**

```json
{
  "type": "object",
  "properties": {
    "doc_id": { "type": "string" },
    "doc_name": { "type": "string" },
    "doc_type": { "type": "string" },
    "total_pages": { "type": "integer" },
    "parsed_pages": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "page": { "type": "integer" },
          "content": { "type": "string" },
          "content_length": { "type": "integer" }
        },
        "required": ["page", "content", "content_length"]
      }
    }
  },
  "required": ["doc_id", "doc_name", "doc_type", "total_pages", "parsed_pages"]
}
```

---

## 五、结束节点（无需代码节点）

| 变量 | 值 |
|------|-----|
| `result` | LLM → **structured_output**（或 **text**） |

---

## 六、后端期望的完整 JSON 示例

```json
{
  "doc_id": "doc_a1b2c3d4e5f6",
  "doc_name": "AI导论.pptx",
  "doc_type": "pptx",
  "total_pages": 2,
  "parsed_pages": [
    {
      "page": 1,
      "content": "第一章 机器学习概述\n- 机器学习是人工智能的分支",
      "content_length": 35
    },
    {
      "page": 2,
      "content": "第二章 监督学习\n- 分类与回归",
      "content_length": 22
    }
  ]
}
```

---

## 七、Dify 内测试（UI 上传）

测试运行输入：

| 字段 | 值 |
|------|-----|
| scene | `parse_document` |
| file | 上传一个 **PDF 或 PPTX** 测试文件 |
| filename | `AI导论.pptx`（与上传文件名一致） |

成功标志：
- `parsed_pages` 至少 1 条
- 每条有 `page`、`content`
- `doc_type` 正确（pdf / pptx）

---

## 八、API 两步验证（模拟 Go 后端）

### 步骤 1：上传文件

```powershell
curl -X POST "http://127.0.0.1:18001/v1/files/upload" `
  -H "Authorization: Bearer app-你的WorkflowKey" `
  -F "file=@C:\path\to\AI导论.pptx" `
  -F "user=test-user"
```

返回 `"id": "xxxxxxxx"`，记下 file_id。

### 步骤 2：运行 workflow

```powershell
curl -X POST "http://127.0.0.1:18001/v1/workflows/run" `
  -H "Authorization: Bearer app-你的WorkflowKey" `
  -H "Content-Type: application/json" `
  -d "{\"inputs\":{\"scene\":\"parse_document\",\"filename\":\"AI导论.pptx\",\"file\":{\"transfer_method\":\"local_file\",\"upload_file_id\":\"替换为file_id\",\"type\":\"document\"}},\"response_mode\":\"blocking\",\"user\":\"test\"}"
```

---

## 九、Go 后端验证

```powershell
cd backend
go run test_workflow_parse_document.go "C:\path\to\AI导论.pptx"
```

脚本会：读本地文件 → 调 Dify 上传 → 调 workflow → 打印 `parsed_pages`。

---

## 十、业务链路说明

课件上传完整链路：

```
ParseDocument（本接口）→ parsed_pages
        ↓
ReconstructDocument（05）→ teaching_nodes
        ↓
GenerateNodeScript（04）→ 节点讲稿
```

后端 `courseService` 在上传课件时自动串联以上三步。

---

## 十一、常见问题

| 问题 | 处理 |
|------|------|
| 文档提取器输出为空 | 检查 file 类型是否为 PDF/PPTX；文件是否损坏 |
| parsed_pages 只有 1 条 | 在 LLM 提示词中强调「按幻灯片/分页拆分」 |
| 页码不准 | 可接受；精确解析仍走 Python fallback |
| workflow 报 file 无效 | 确认开始节点变量名是 `file`，且 upload_file_id 未过期 |

---

## 十二、完成标志

- [ ] 开始节点有 `file`（单文件）+ `filename`
- [ ] IF/ELSE 新增 `parse_document` 分支
- [ ] 文档提取器 → LLM → 结束 跑通
- [ ] 测试返回 `parsed_pages`
- [ ] Go `ParseDocument` 不再走 Python 降级

完成后继续：**07-generate_audio.md**
