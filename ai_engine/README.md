# AI Engine - 解析与生成模块

## 当前能力

- 支持 PDF 按页解析
- 支持 PPTX 按页（幻灯片）解析
- 返回统一结构化 JSON（含 `doc_id`、`total_pages`、`parsed_pages`、`stats`）
- 支持生成每页的讲稿与思维导图结构（`mock` / `llm`）
- 支持命令行输出到控制台或写入 JSON 文件

## 目录

- `parser.py`：解析入口与命令行运行器
- `schema.py`：统一结构化输出协议
- `generator.py`：讲稿与导图生成器
- `generate.py`：解析+生成一体化 CLI
- `qa.py`：问答溯源与重讲逻辑
- `ask.py`：问答测试 CLI

## 快速运行

```powershell
conda activate fuww_ai
python ai_engine\parser.py <你的PDF或PPTX路径>
```

输出到文件：

```powershell
conda activate fuww_ai
python ai_engine\parser.py <你的PDF或PPTX路径> --out ai_engine\result.json
```

## 生成讲稿与导图

使用 `mock`（本地可直接跑）：

```powershell
conda activate fuww_ai
python ai_engine\generate.py <你的PDF或PPTX路径> --mode mock --out ai_engine\generated.json
```

使用 `llm`（真实大模型）：

```powershell
conda activate fuww_ai
set AI_API_KEY=你的APIKEY
set AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
python ai_engine\generate.py <你的PDF或PPTX路径> --mode llm --model qwen-plus --out ai_engine\generated_llm.json
```

## 输出协议（示例字段）

- `doc_id`: 文档唯一 ID
- `doc_name`: 文件名
- `doc_type`: `pdf` 或 `pptx`
- `total_pages`: 总页数
- `parsed_pages`: 页级内容数组（`page`, `content`, `content_length`）
- `stats`: 统计信息（`non_empty_pages`, `empty_pages`, `elapsed_ms`）

`generate.py` 输出为：

- `parsed`: 解析结果
- `generated.lessons`: 每页生成内容，包含 `script` 与 `mindmap_markdown`

## 问答溯源与重讲

使用 `mock`：

```powershell
conda activate fuww_ai
python ai_engine\ask.py ai_engine\_tmp_test.json "这一页在讲什么" --page 1 --mode mock
python ai_engine\ask.py ai_engine\_tmp_test.json "我听不懂，换个例子" --page 1 --mode mock
```

使用 `llm`：

```powershell
conda activate fuww_ai
set AI_API_KEY=你的APIKEY
set AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
python ai_engine\ask.py ai_engine\_tmp_test.json "这个公式为什么这样推导" --page 2 --mode llm --model qwen-plus
```

`ask.py` 输出字段：

- `source_page`: 溯源页码
- `intent.need_reteach`: 是否触发重讲
- `answer`: 回答文本
- `resume_page`: 问答结束后建议续播页

## 手动验收与调试

一键跑通本地验收（会自动生成测试 PDF/PPTX 并输出结果文件）：

```powershell
conda activate fuww_ai
python ai_engine\debug_harness.py
```

验收输出目录：`ai_engine/debug_output`

- `parsed_pdf.json` / `parsed_pptx.json`：解析结果
- `generated_pdf_mock.json`：讲稿+导图生成结果
- `qa_normal.json` / `qa_reteach.json`：问答结果
- `summary.json`：验收检查项通过情况

建议你重点看 `summary.json` 的这些项：

- 解析是否成功（PDF/PPTX）
- 是否有 `script` 与 `mindmap_markdown`
- 是否能触发 `need_reteach=true`
- 是否返回 `source_page` 用于溯源

## 下一步

- 增加问答溯源（按页上下文回答）
- 加入评测指标与鲁棒性优化
