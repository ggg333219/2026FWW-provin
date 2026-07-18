# 任务包 B — Python AI Engine

> 负责人：同学 B  |  预估工作量：密集 1.5 周

## 你的职责

AI Engine 是系统**大脑**：所有 LLM 调用、文档解析、课件生成、知识库 RAG 都在这里。你需要把现有的平铺式代码重组为按 Skill 分组的模块，并实现 S2/S3/KB 的核心能力。

**你不需要碰**：Go 后端的改造（同学 A 管）、前端页面（同学 C 管）。你只需要保证 AI Engine 接口稳定、功能正确。

---

## 现有代码概况

```
ai_engine/
├── main.py               # FastAPI 入口 (543 行) — 所有路由在同一个文件
├── schema.py             # 数据模型 (486 行)
├── generator.py          # 脚本生成逻辑 (689 行) — 需重构
├── qa.py                 # 问答+LLM 调用 (约 200 行)
├── parser.py             # 文档解析 PDF/PPTX (297 行)
├── reconstructor.py      # 文档重建 (约 200 行)
├── document_parser.py    # 另一份文档解析 (约 250 行)
└── recommendation/
    └── service.py        # 推荐服务 (665 行) — 暂不动
```

**关键问题**：
1. 所有路由集中在 `main.py`，难以维护
2. LLM 调用分散在各文件，没有统一封装
3. 无视频解析、OCR、RAG 能力
4. 使用内存字典做存储（重启丢失）

**现有能力评估**（哪些能用，哪些要重写）：

| 能力 | 状态 | 复用策略 |
|------|------|---------|
| PDF 解析 | ✅ 已有 DocumentParser | 直接复用，补充异常页兜底 |
| PPT 解析 | ✅ 已支持 pptx（含 notes） | 直接复用，补充图文布局提取 |
| 讲稿生成 | ✅ 已有 LessonGenerator | 复用并扩展，增加风格控制参数 |
| 问答（含重讲） | ✅ 已有 QAResponder | 从学生问答重构为教师需求澄清 |
| Markdown 三阶段生成 | ✅ 已有 generate-from-markdown | 直接复用，作为新 Agent 中间结构层 |
| 节点重构 | ✅ 已有 reconstruct-document | 与版本管理结合，支持局部再生成 |
| 音频生成 | ✅ 已有（mock/openai-tts） | 演示增强项，非首要里程碑 |
| 知识点树解析 | ✅ 已有 parse-knowledge | 与知识库入库流程打通 |
| 视频解析 | ❌ 缺失 | 新增 |
| Word 教案生成 | ❌ 缺失 | 新增 |
| PPT 成品导出 | ❌ 缺失 | 新增 |
| RAG 知识库 | ❌ 缺失 | 新增 |

**顺手修的两个 bug**（代码里已验证）：
- `ai_engine/generate.py` 中使用了 `os.getenv` 但顶部没有 `import os`
- `ai_engine/ask.py` 同样缺少 `import os`

---

## 任务分解

### B1. AI Engine 目录重组 ⭐（先做，为后续打基础）

**目标**：从平铺结构改为按域分组。

**操作**：

创建以下目录结构，把现有文件拆分进去：

```
ai_engine/
├── main.py                # 保留，精简为只 import 各模块 router
├── core/                  # （新增）核心基础设施
│   ├── __init__.py
│   ├── llm.py             # 从 qa.py 提取 LLM 调用统一封装
│   ├── config.py          # 从 main.py 提取配置
│   └── sse.py             # SSE 流式协议封装
├── intent/                # （新增）S1 意图理解
│   ├── __init__.py
│   ├── router.py          # 路由（挂载到 /api/v1/intent）
│   ├── extractor.py       # LLM 意图提取
│   ├── fields.py          # 字段定义和优先级
│   └── prompts/           # 提示词模板
├── parse/                 # （扩展）S2 多模态解析
│   ├── __init__.py
│   ├── doc.py             # 从 parser.py/document_parser.py 合并
│   ├── video.py           # （新增）视频关键帧+ASR
│   ├── ocr.py             # （新增）图片 OCR
│   ├── normalizer.py      # （新增）统一分块标准化
│   └── mapper.py          # （新增）材料-块-意图映射
├── gen/                   # （重构）S3 课件生成
│   ├── __init__.py
│   ├── outline.py         # （新增）大纲构建
│   ├── node.py            # 从 generator.py 提取
│   ├── modify.py          # （新增）修改引擎
│   ├── export_ppt.py      # （新增）PPT 导出（python-pptx）
│   ├── export_doc.py      # （新增）Word 导出（python-docx）
│   ├── interactive.py     # （新增）互动内容生成
│   ├── preview.py         # （新增）HTML 预览生成
│   └── templates/         # （新增）模板资产
├── rag/                   # （新增）知识库 RAG
│   ├── __init__.py
│   ├── chunker.py         # 分块
│   ├── embed.py           # 向量化
│   ├── store.py           # pgvector 存储
│   ├── retrieve.py        # 混合检索
│   ├── rerank.py          # 重排序
│   └── evidence.py        # 证据融合
└── recommendation/        # 保留不动
    └── service.py
```

**拆法**：
1. 先在 `core/llm.py` 封装统一的 LLM 调用函数，复用 `qa.py` 中的 `resolve_llm_base_url()` 和客户端初始化
2. `main.py` 改成只注册路由，不写具体逻辑
3. 现有文件先复制进去，再逐步精简

**完成标志**：`uvicorn main:app` 启动正常，所有原接口仍然可用。

### B2. 统一 LLM 调用封装 ⭐

**目标**：不再到处写 OpenAI 客户端初始化。

**在 `core/llm.py` 中**：

```python
class LLMClient:
    def __init__(self, config: LLMConfig):
        self.client = OpenAI(...)
    
    def chat(self, messages, response_format=None, temperature=0.1) -> str | dict:
        """统一调用入口，支持 JSON mode"""
        
    def chat_stream(self, messages) -> Generator[str, None, None]:
        """流式调用"""
```

**复用来源**：`qa.py` 中的 `resolve_llm_base_url()`、客户端初始化、`_extract_json()` 回退函数。

**完成标志**：所有模块通过 `core.llm.LLMClient` 调用 LLM，无散落初始化。

### B3. S2 多模态解析 — 视频处理器

**目标**：支持上传视频 → 抽取关键帧 + ASR 字幕文本。

**依赖**：系统需安装 FFmpeg。

**在 `parse/video.py` 中**：

```python
def extract_frames(video_path, interval_sec=30) -> List[Frame]:
    """FFmpeg 每隔 N 秒抽一帧"""

def extract_asr(video_path) -> List[TranscriptSegment]:
    """Whisper 转录音频"""

def understand_frame(frame: Frame, vlm_client) -> str:
    """可选：用 VLM (GLM-4V) 理解帧内容"""
```

**接口路由**（挂 `parse/router.py` 或直接 `main.py`）：
```
POST /api/v1/parse/video  — 上传视频 → 解析
GET  /api/v1/parse/status/:task_id — 查询解析状态
```

**完成标志**：上传视频可输出 ASR 文本 + 关键帧描述。

### B4. S2 多模态解析 — OCR 引擎

**目标**：支持图片 OCR + 版面分析。

**在 `parse/ocr.py` 中**：

```python
def ocr_image(image_path) -> List[OCRResult]:
    """PaddleOCR 或 Tesseract"""

def analyze_layout(image_path) -> Layout:
    """版面分析：标题区/正文区/表格区"""
```

**完成标志**：上传图片可提取文字内容。

### B5. S2 多模态解析 — 分块标准化 + 材料映射

**目标**：把各种解析结果统一成标准分块格式，并关联到教学意图。

**在 `parse/normalizer.py` 中**：

```python
# 统一分块 schema
class Chunk(BaseModel):
    chunk_id: str
    source_type: str  # "pdf" | "pptx" | "docx" | "image" | "video"
    content: str
    page_ref: int | None
    metadata: dict
    embedding: List[float] | None = None
```

**在 `parse/mapper.py` 中**：

```python
class MaterialMapper:
    def map_to_intent(self, chunks, intent_id) -> MaterialIntentMap:
        """构建映射关系"""
```

### B6. KB 知识库 RAG — 分块管道

**目标**：把解析后的文档切分成语义块，为向量化做准备。

**在 `rag/chunker.py` 中**：

```python
def chunk_document(text: str, doc_type: str) -> List[Chunk]:
    """
    PDF/DOCX: 按段落+标题层级，512 tokens，64 overlap
    PPTX: 按页，每页独立
    图片: 按版面区域
    视频: 按 30s 窗口
    """
```

**完成标志**：输入文本可输出符合策略的分块。

### B7. KB 知识库 RAG — 向量存储

**目标**：用 pgvector（PostgreSQL 扩展）存储和检索向量。

**为什么选 pgvector**：系统已用 PostgreSQL，无需额外部署 Milvus/Qdrant。pgvector 0.8+ 支持 HNSW 索引。

**在 `rag/store.py` 中**：

```python
class VectorStore:
    def store_chunks(self, chunks: List[Chunk]):
        """写入 pgvector"""
    
    def similarity_search(self, embedding, top_k=20) -> List[Chunk]:
        """余弦相似度搜索"""
```

**在 `rag/embed.py` 中**：

```python
class EmbeddingService:
    def embed(self, text: str) -> List[float]:
        """调用嵌入 API"""
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入"""
```

### B8. KB 知识库 RAG — 混合检索

**目标**：向量检索 + BM25 关键词检索融合。

**在 `rag/retrieve.py` 中**：

```python
def hybrid_retrieve(query, top_k=20):
    """
    score = 0.7 * cosine_sim(embedding(q), embedding(chunk))
           + 0.3 * bm25_score(q, chunk)
    低于 0.6 阈值的结果丢弃
    """
```

**在 `rag/rerank.py` 中**：

```python
def rerank(chunks: List[Chunk], query: str, top_k=5) -> List[Chunk]:
    """可选 cross-encoder 重排序"""
```

### B9. KB 知识库 RAG — 证据融合

**目标**：把检索结果+LLM 合成 → `evidence_packet` 供 S3 生成使用。

**在 `rag/evidence.py` 中**：

```python
def synthesize_evidence(query, retrieved_chunks, intent_context) -> EvidencePacket:
    """
    返回:
    {
        "relevant_chunks": [top-5 chunks],
        "synthesized_context": "LLM 生成的摘要...",
        "citations": [{"chunk_id", "text_snippet", "source_ref"}]
    }
    """
```

### B10. S3 课件生成 — 大纲构建

**目标**：从意图摘要 + 证据包生成课件大纲。

**在 `gen/outline.py` 中**：

```python
def build_outline(intent, evidence_packet) -> List[OutlineNode]:
    """LLM 调用生成大纲结构"""
```

**输入**：S1 的结构化意图 + KB 的证据包
**输出**：节点数组（含标题、内容要点、引用源）

### B11. S3 课件生成 — 节点生成

**目标**：逐节点生成课件内容。

**在 `gen/node.py` 中**：

从现有 `generator.py` 重构提取。核心逻辑保持，包装成：

```python
def generate_node(node_info, intent, evidence) -> TeachingNode:
    """单节点生成（可按节点并行）"""
```

**复用现有代码**：`generator.py` 中的 `AIScriptGenerator` 类、`TeachingNode` 模型。

### B12. S3 课件生成 — PPT/DOC 导出

**目标**：把结构化节点导出为 PPTX/DOCX 文件。

**在 `gen/export_ppt.py` 中**：

```python
def export_to_pptx(nodes, template_id="default") -> str:
    """
    1. 加载模板
    2. 遍历节点，按类型选择 slide layout
    3. 填充内容
    4. 保存到 MinIO
    """
```

依赖：`python-pptx` 库。

**在 `gen/export_doc.py` 中**：

```python
def export_to_docx(nodes) -> str:
    """
    1. 创建文档
    2. 逐节写入
    3. 保存到 MinIO
    """
```

依赖：`python-docx` 库。

**完成标志**：节点数组 → 下载可打开的 PPTX/DOCX 文件。

### B13. S3 课件生成 — 互动内容

**目标**：在课件中嵌入测验、投票等互动元素。

**在 `gen/interactive.py` 中**：

```python
def generate_quiz(node_content) -> Quiz:
def generate_flashcard(node_content) -> FlashCard:
```

### B14. AI Engine 主路由注册

**目标**：把所有新模块的路由注册到 FastAPI。

**在 `main.py` 中**：

```python
from core.router import core_router
from intent.router import intent_router
from parse.router import parse_router
from gen.router import gen_router
from rag.router import rag_router

app.include_router(core_router, prefix="/api/v1")
app.include_router(intent_router, prefix="/api/v1/intent")
app.include_router(parse_router, prefix="/api/v1/parse")
app.include_router(gen_router, prefix="/api/v1/gen")
app.include_router(rag_router, prefix="/api/v1/rag")
```

---

## 检验清单

| 任务 | 检验方式 | 预计耗时 |
|------|---------|---------|
| B1 目录重组 | 服务启动正常，原接口可用 | 半天 |
| B2 LLM 统一封装 | 各模块通过 LLMClient 调用 | 半天 |
| B3 视频解析 | FFmpeg + Whisper 解析视频 | 1 天 |
| B4 OCR 引擎 | 图片 OCR 输出准确 | 半天 |
| B5 分块标准化 | 多源输入→统一 Chunk | 半天 |
| B6 RAG 分块管道 | 文档→语义块 | 半天 |
| B7 向量存储 | pgvector 读写正常 | 半天 |
| B8 混合检索 | 检索结果相关度高 | 1 天 |
| B9 证据融合 | 输出完整 evidence_packet | 半天 |
| B10 大纲构建 | 意图+证据→结构化大纲 | 1 天 |
| B11 节点生成 | 大纲→完整节点内容 | 1 天 |
| B12 PPT/DOC 导出 | 生成可打开的文件 | 1.5 天 |
| B13 互动内容 | 嵌入选择题/测验 | 半天 |
| B14 路由注册 | 所有端点可用 | 2 小时 |

## 如何与同学 A 对接

- 同学 A 通过 HTTP 调用你的接口，基础 URL 就是你的 FastAPI 地址
- 你先实现接口，可以返回 mock 数据让同学 A 先调通
- 接口格式见 `005-接口契约手册.md`
- 所有 AI Engine 接口按 RESTful 风格，返回 JSON

## 如何与同学 C 对接

- 同学 C 只调同学 A 的 Go 后端，不直接调 AI Engine
- 所以你只需要保持与同学 A 的接口稳定即可
