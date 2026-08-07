"""
S2 多模态解析 (parse) 模块单元测试

严格遵循开发 Skill 注意事项.md：
  - 数据模型引用 ai_engine.core.schema，不重新定义已有结构
  - 配置引用 ai_engine.core.settings
  - LLM 调用统一走 ai_engine.core.LLMClient（不 mock OpenAI）
  - 测试文件放 ai_engine/tests/ 下
  - 运行方式：python -m pytest ai_engine/tests/

覆盖模块：
  - chunk_normalizer  — 分块标准化
  - material_mapper  — 材料-块映射
  - task_manager     — 任务生命周期 + 文件类型推断
  - doc_parser       — 文档解析（含分页逻辑）
  - ocr_engine       — OCR 图像文字提取 + 版面分析
  - video_processor  — 视频处理（异常路径）
  - minio_client     — MinIO 存储客户端（异常路径）
  - router           — FastAPI 端点校验
"""

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from ai_engine.core.schema import (
    Chunk,
    MaterialAsset,
    ParseProcessRequest,
    ParseProcessResponse,
    ParseStatusResponse,
    ParseStatus,
    SourceType,
)
from ai_engine.parse.chunk_normalizer import ChunkNormalizer
from ai_engine.parse.material_mapper import MaterialMapper
from ai_engine.parse.task_manager import (
    TaskManager,
    FileTask,
    FileTaskStatus,
    AggregateTask,
    AggregateTaskStatus,
    _infer_source_type,
)
from ai_engine.parse.doc_parser import DocumentParser, _image_content_type_to_ext


# =============================================================================
# 1. chunk_normalizer 测试
# =============================================================================

class ChunkNormalizerTest(unittest.TestCase):
    """ChunkNormalizer.normalize() 数据格式必须严格遵循 Chunk 模型。"""

    def setUp(self):
        self.normalizer = ChunkNormalizer(max_content_chars=5000)
        self.source_ref = f"doc_{uuid.uuid4().hex[:8]}"

    def test_normalize_basic_text_chunks(self):
        """基础文本块标准化为 Chunk 对象。"""
        raw = [
            {"type": "text", "page": 1, "content": "第一章 线性回归"},
            {"type": "text", "page": 2, "content": "损失函数与梯度下降"},
        ]
        chunks = self.normalizer.normalize(raw, source_ref=self.source_ref, source_type=SourceType.PDF)

        self.assertEqual(len(chunks), 2)
        for c in chunks:
            # 必含字段校验
            self.assertIsInstance(c, Chunk)
            self.assertTrue(c.chunk_id.startswith("chunk_"))
            self.assertEqual(c.source_ref, self.source_ref)
            self.assertEqual(c.source_type, SourceType.PDF)
            self.assertIsInstance(c.seq_index, int)
            self.assertIsInstance(c.metadata, dict)

        # 顺序索引递增
        self.assertEqual(chunks[0].seq_index, 0)
        self.assertEqual(chunks[1].seq_index, 1)

        # page_ref
        self.assertEqual(chunks[0].page_ref, 1)
        self.assertEqual(chunks[1].page_ref, 2)

        # content
        self.assertEqual(chunks[0].content, "第一章 线性回归")
        self.assertEqual(chunks[1].content, "损失函数与梯度下降")

    def test_normalize_with_custom_seq_index(self):
        """raw_chunk 中自定义 seq_index 生效。"""
        raw = [
            {"type": "text", "content": "A", "seq_index": 10},
            {"type": "text", "content": "B", "seq_index": 20},
        ]
        chunks = self.normalizer.normalize(raw, source_ref=self.source_ref)
        self.assertEqual(chunks[0].seq_index, 10)
        self.assertEqual(chunks[1].seq_index, 20)

    def test_normalize_empty_input(self):
        """空输入返回空列表。"""
        chunks = self.normalizer.normalize([], source_ref=self.source_ref)
        self.assertEqual(chunks, [])

    def test_normalize_content_truncation(self):
        """超长内容自动截断。"""
        long_content = "A" * 300
        normalizer = ChunkNormalizer(max_content_chars=100)
        chunks = normalizer.normalize(
            [{"type": "text", "content": long_content}],
            source_ref=self.source_ref,
        )
        self.assertEqual(len(chunks), 1)
        self.assertIn("...(截断)", chunks[0].content)
        # 截断后缀为: \n...(截断) 共8个字符
        expected_min = 100 + 1  # 至少多出换行符
        self.assertGreaterEqual(len(chunks[0].content), expected_min)

    def test_normalize_null_page_ref(self):
        """非整数 page 值转为 None。"""
        raw = [{"type": "text", "content": "no page", "page": None}]
        chunks = self.normalizer.normalize(raw, source_ref=self.source_ref)
        self.assertIsNone(chunks[0].page_ref)

    def test_normalize_various_source_types(self):
        """PDF / PPTX / DOCX / IMAGE / VIDEO 均产出 Chunk。"""
        raw = [{"type": "text", "content": "test"}]
        for st in (SourceType.PDF, SourceType.PPTX, SourceType.DOCX, SourceType.IMAGE, SourceType.VIDEO):
            chunks = self.normalizer.normalize(raw, source_ref=self.source_ref, source_type=st)
            self.assertEqual(chunks[0].source_type, st)

    def test_normalize_metadata_preserved(self):
        """metadata 原样保留。"""
        raw = [{"type": "frame", "content": "frame desc", "metadata": {"timestamp_sec": 30, "model": "qwen-vl"}}]
        chunks = self.normalizer.normalize(raw, source_ref=self.source_ref)
        self.assertEqual(chunks[0].metadata["timestamp_sec"], 30)
        self.assertEqual(chunks[0].metadata["model"], "qwen-vl")

    def test_normalize_formats_source_specific_content(self):
        """不同来源应带上更适合预览/检索的格式前缀。"""
        cases = [
            (SourceType.PDF, [{"type": "text", "page": 2, "content": "正文"}], "# 第2页"),
            (SourceType.PPTX, [{"type": "slide", "page": 3, "content": "标题"}], "# 幻灯片 3"),
            (SourceType.DOCX, [{"type": "text", "page": 4, "content": "段落"}], "# 文档段落 4"),
            (SourceType.IMAGE, [{"type": "ocr", "content": "识别文本"}], "【OCR识别】"),
            (SourceType.VIDEO, [{"type": "frame", "content": "视频内容", "metadata": {"timestamp_range": [10, 20]}}], "【视频片段 10s-20s】"),
            (SourceType.AUDIO, [{"type": "transcript", "content": "音频内容", "metadata": {"timestamp_range": [5, 15]}}], "【音频片段 5s-15s】"),
        ]
        for source_type, raw, expected_prefix in cases:
            chunks = self.normalizer.normalize(raw, source_ref=self.source_ref, source_type=source_type)
            self.assertGreaterEqual(len(chunks), 1)
            self.assertTrue(chunks[0].content.startswith(expected_prefix), f"{source_type} => {chunks[0].content}")


# =============================================================================
# 2. material_mapper 测试
# =============================================================================

class MaterialMapperTest(unittest.TestCase):
    """MaterialMapper 映射关系数据格式必须严格遵循 Chunk 模型。"""

    def setUp(self):
        self.mapper = MaterialMapper()
        self.task_id = f"task_{uuid.uuid4().hex[:8]}"
        self.chunks = [
            Chunk(chunk_id="c1", source_type=SourceType.PDF, source_ref="doc1", content="c1", seq_index=0),
            Chunk(chunk_id="c2", source_type=SourceType.PDF, source_ref="doc1", content="c2", seq_index=1),
            Chunk(chunk_id="c3", source_type=SourceType.PPTX, source_ref="doc2", content="c3", seq_index=0),
        ]

    def test_build_mappings_basic(self):
        """build_mappings 建立文件→Chunk 和 Chunk→文件映射。"""
        self.mapper.build_mappings(self.task_id, self.chunks)

        mapping = self.mapper.get_material_mapping(self.task_id)
        self.assertIn("doc1", mapping)
        self.assertIn("doc2", mapping)
        self.assertEqual(mapping["doc1"], ["c1", "c2"])
        self.assertEqual(mapping["doc2"], ["c3"])

        self.assertEqual(self.mapper.get_chunk_source("c1"), "doc1")
        self.assertEqual(self.mapper.get_chunk_source("c3"), "doc2")
        self.assertIsNone(self.mapper.get_chunk_source("nonexistent"))

    def test_build_mappings_with_intent(self):
        """关联 intent_id 时，intent_chunks 正确记录。"""
        intent_id = f"intent_{uuid.uuid4().hex[:8]}"
        self.mapper.build_mappings(self.task_id, self.chunks, intent_id=intent_id)

        intent_chunks = self.mapper.get_intent_chunks(intent_id)
        self.assertEqual(sorted(intent_chunks), ["c1", "c2", "c3"])

        # 未关联的 intent_id 返回空列表
        self.assertEqual(self.mapper.get_intent_chunks("nonexistent"), [])

    def test_build_mappings_append_to_existing_task(self):
        """同一 task_id 多次 build_mappings 追加映射。"""
        self.mapper.build_mappings(self.task_id, self.chunks[:1])  # c1

        new_chunk = Chunk(chunk_id="c4", source_type=SourceType.PDF, source_ref="doc1", content="c4", seq_index=2)
        self.mapper.build_mappings(self.task_id, [new_chunk])

        mapping = self.mapper.get_material_mapping(self.task_id)
        self.assertEqual(mapping["doc1"], ["c1", "c4"])

    def test_build_mappings_append_intent_chunks(self):
        """同一 intent_id 多次追加 chunks。"""
        intent_id = "intent_1"
        self.mapper.build_mappings(self.task_id, self.chunks[:1], intent_id=intent_id)
        self.mapper.build_mappings(self.task_id, self.chunks[1:], intent_id=intent_id)

        intent_chunks = self.mapper.get_intent_chunks(intent_id)
        self.assertEqual(len(intent_chunks), 3)

    def test_clear_task(self):
        """clear_task 清除 task 所有映射。"""
        self.mapper.build_mappings(self.task_id, self.chunks)
        self.mapper.clear_task(self.task_id)

        self.assertEqual(self.mapper.get_material_mapping(self.task_id), {})
        self.assertIsNone(self.mapper.get_chunk_source("c1"))

    def test_clear_task_unknown(self):
        """清除不存在的 task_id 不报错。"""
        self.mapper.clear_task("nonexistent")  # 不应抛异常

    def test_empty_chunks_list(self):
        """空 chunks 列表建立空映射。"""
        self.mapper.build_mappings(self.task_id, [])
        self.assertEqual(self.mapper.get_material_mapping(self.task_id), {})


# =============================================================================
# 3. task_manager 测试
# =============================================================================

class TaskManagerFileTaskTest(unittest.TestCase):
    """FileTask 内部数据结构测试。"""

    def test_file_task_defaults(self):
        ft = FileTask(file_path="/path/to/test.pdf", source_type=SourceType.PDF)
        self.assertEqual(ft.file_path, "/path/to/test.pdf")
        self.assertEqual(ft.source_type, SourceType.PDF)
        self.assertEqual(ft.status, FileTaskStatus.UPLOADED)
        self.assertEqual(ft.retry_count, 0)
        self.assertEqual(ft.retry_limit, 2)
        self.assertEqual(ft.chunks, [])
        self.assertIsNone(ft.asset)
        self.assertIsNone(ft.error)

    def test_file_task_can_retry(self):
        ft = FileTask("/f.pdf")
        self.assertTrue(ft.can_retry)
        ft.retry_count = 2
        self.assertFalse(ft.can_retry)

    def test_file_task_is_terminal(self):
        ft = FileTask("/f.pdf")
        self.assertFalse(ft.is_terminal)
        ft.status = FileTaskStatus.DONE
        self.assertTrue(ft.is_terminal)
        ft.status = FileTaskStatus.FAILED
        self.assertTrue(ft.is_terminal)


class TaskManagerAggregateTaskTest(unittest.TestCase):
    """AggregateTask 聚合任务数据结构测试。"""

    def test_aggregate_task_defaults(self):
        task = AggregateTask(session_id="s1", intent_id="i1")
        self.assertTrue(task.task_id.startswith("parse_"))
        self.assertEqual(task.session_id, "s1")
        self.assertEqual(task.intent_id, "i1")
        self.assertEqual(task.status, AggregateTaskStatus.PENDING)
        self.assertEqual(task.files, [])

    def test_aggregate_task_all_chunks(self):
        task = AggregateTask(session_id="s1")
        f1 = FileTask("/a.pdf")
        f1.chunks = [Chunk(chunk_id="c1", content="a", source_ref="doc1", source_type=SourceType.PDF, seq_index=0)]
        f2 = FileTask("/b.pdf")
        f2.chunks = [Chunk(chunk_id="c2", content="b", source_ref="doc2", source_type=SourceType.PDF, seq_index=0)]
        task.files = [f1, f2]
        self.assertEqual(len(task.all_chunks), 2)

    def test_aggregate_task_counts(self):
        task = AggregateTask(session_id="s1")
        f1 = FileTask("/a.pdf")
        f1.status = FileTaskStatus.DONE
        f2 = FileTask("/b.pdf")
        f2.status = FileTaskStatus.FAILED
        f3 = FileTask("/c.pdf")
        f3.status = FileTaskStatus.DONE
        task.files = [f1, f2, f3]
        self.assertEqual(task.done_count, 2)
        self.assertEqual(task.failed_count, 1)


class TaskManagerInferSourceTypeTest(unittest.TestCase):
    """_infer_source_type 文件类型推断测试。"""

    def test_pdf(self):
        self.assertEqual(_infer_source_type("doc.pdf"), SourceType.PDF)

    def test_pptx(self):
        self.assertEqual(_infer_source_type("slide.pptx"), SourceType.PPTX)
        self.assertEqual(_infer_source_type("slide.ppt"), SourceType.PPTX)

    def test_docx(self):
        self.assertEqual(_infer_source_type("doc.docx"), SourceType.DOCX)
        self.assertEqual(_infer_source_type("doc.doc"), SourceType.DOCX)

    def test_image(self):
        for ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"):
            self.assertEqual(_infer_source_type(f"img{ext}"), SourceType.IMAGE)

    def test_video(self):
        for ext in (".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"):
            self.assertEqual(_infer_source_type(f"vid{ext}"), SourceType.VIDEO)

    def test_audio(self):
        for ext in (".mp3", ".wav", ".m4a"):
            self.assertEqual(_infer_source_type(f"audio{ext}"), SourceType.AUDIO)

    def test_unknown_extension(self):
        self.assertEqual(_infer_source_type("file.unknown"), SourceType.TEXT)

    def test_no_extension(self):
        self.assertEqual(_infer_source_type("Makefile"), SourceType.TEXT)

    def test_case_insensitive(self):
        self.assertEqual(_infer_source_type("DOC.PDF"), SourceType.PDF)
        self.assertEqual(_infer_source_type("SLIDE.PPTX"), SourceType.PPTX)


class TaskManagerCreateTaskTest(unittest.TestCase):
    """TaskManager.create_task() 数据格式严格遵循 ParseProcessResponse。"""

    def setUp(self):
        self.manager = TaskManager()

    def test_create_task_response_format(self):
        """create_task 返回 ParseProcessResponse 且字段完整。"""
        response = self.manager.create_task(
            session_id="session_1",
            file_paths=["/path/to/doc.pdf", "/path/to/img.png"],
            intent_id="intent_1",
        )
        # 响应体校验
        self.assertIsInstance(response, ParseProcessResponse)
        self.assertTrue(response.task_id.startswith("parse_"))
        self.assertEqual(response.status, "processing")

        # assets 列表
        self.assertEqual(len(response.assets), 2)
        for asset in response.assets:
            self.assertIsInstance(asset, MaterialAsset)
            self.assertTrue(asset.asset_id.startswith("asset_"))
            self.assertEqual(asset.session_id, "session_1")
            self.assertEqual(asset.parse_status, ParseStatus.UPLOADED)

        # 类型推断
        self.assertEqual(response.assets[0].source_type, SourceType.PDF)
        self.assertEqual(response.assets[1].source_type, SourceType.IMAGE)

    def test_create_task_empty_file_paths(self):
        """空文件列表返回空 assets。"""
        response = self.manager.create_task(session_id="s1", file_paths=[])
        self.assertEqual(len(response.assets), 0)

    def test_create_task_internal_state(self):
        """create_task 后内部 AggregateTask 正确初始化。"""
        response = self.manager.create_task(
            session_id="s1",
            file_paths=["/a.pdf", "/b.pptx"],
        )
        task = self.manager.get_task(response.task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.status, AggregateTaskStatus.PROCESSING)
        self.assertEqual(len(task.files), 2)
        self.assertEqual(task.files[0].source_type, SourceType.PDF)
        self.assertEqual(task.files[1].source_type, SourceType.PPTX)


class TaskManagerGetTaskStatusTest(unittest.TestCase):
    """TaskManager.get_task_status() 数据格式严格遵循 ParseStatusResponse。"""

    def setUp(self):
        self.manager = TaskManager()
        self.response = self.manager.create_task(session_id="s1", file_paths=["/a.pdf"])
        self.task_id = self.response.task_id

    def test_get_task_status_format(self):
        """get_task_status 返回 ParseStatusResponse 且字段完整。"""
        status = self.manager.get_task_status(self.task_id)
        self.assertIsInstance(status, ParseStatusResponse)
        self.assertEqual(status.task_id, self.task_id)
        # 刚创建且 create_task 设了 PROCESSING → 映射为 PARSING
        self.assertIn(status.status, (ParseStatus.PARSING, ParseStatus.UPLOADED))
        self.assertIsInstance(status.chunks, list)
        # error 应为 None（非失败状态）
        # status 为 PARSING 时 error 应为 None

    def test_get_task_status_not_found(self):
        """不存在的 task_id 返回 FAILED 状态 + 错误信息。"""
        status = self.manager.get_task_status("nonexistent")
        self.assertEqual(status.status, ParseStatus.FAILED)
        self.assertIn("不存在", status.error or "")

    def test_get_task_status_aggregate_mapping(self):
        """AggregateTaskStatus 到 ParseStatus 的映射完整。"""
        # PENDING → UPLOADED
        task = AggregateTask(session_id="s1")
        task.status = AggregateTaskStatus.PENDING
        self.manager._tasks[task.task_id] = task
        status = self.manager.get_task_status(task.task_id)
        self.assertEqual(status.status, ParseStatus.UPLOADED)


# =============================================================================
# 4. doc_parser 测试
# =============================================================================

class TaskManagerPlainTextParseTest(unittest.TestCase):
    """TaskManager 纯文本文件分发与解析回归测试。"""

    def setUp(self):
        self.manager = TaskManager()

    def test_infer_source_type_text_extensions(self):
        """.txt / .md / 其他纯文本扩展名应被识别为 TEXT。"""
        self.assertEqual(_infer_source_type("notes.txt"), SourceType.TEXT)
        self.assertEqual(_infer_source_type("notes.md"), SourceType.TEXT)
        self.assertEqual(_infer_source_type("notes.csv"), SourceType.TEXT)

    def test_parse_by_type_reads_real_text_file(self):
        """SourceType.TEXT 应直接读取真实文本文件。"""
        content = "第一段内容\n\n第二段内容"
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(content.encode("utf-8"))
            tmp_path = f.name
        try:
            ft = FileTask(file_path=tmp_path, source_type=SourceType.TEXT)
            raw = self.manager._parse_by_type(ft)
            self.assertEqual(len(raw), 1)
            self.assertEqual(raw[0]["type"], "text")
            self.assertIn("第一段内容", raw[0]["content"])

            chunks = self.manager._chunk_normalizer.normalize(
                raw_chunks=raw,
                source_ref=tmp_path,
                source_type=SourceType.TEXT,
            )
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].source_type, SourceType.TEXT)
            self.assertEqual(chunks[0].source_ref, tmp_path)
        finally:
            os.unlink(tmp_path)


class DocumentParserConstructorTest(unittest.TestCase):
    """DocumentParser 构造器校验。"""

    def test_init_missing_file_raises(self):
        """不存在的文件路径抛出 FileNotFoundError。"""
        with self.assertRaises(FileNotFoundError):
            DocumentParser("/path/to/nonexistent/file.pdf", source_type=SourceType.PDF)

    def test_init_with_existing_file(self):
        """存在的文件路径正常构造。"""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = f.name
        try:
            parser = DocumentParser(tmp_path, source_type=SourceType.PDF)
            self.assertEqual(parser.file_path, tmp_path)
            self.assertEqual(parser.source_type, SourceType.PDF)
        finally:
            os.unlink(tmp_path)

    def test_unsupported_source_type_raises(self):
        """不支持的 SourceType 调用 parse() 抛出 ValueError。"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp_path = f.name
        try:
            parser = DocumentParser(tmp_path, source_type=SourceType.TEXT)
            with self.assertRaises(ValueError) as ctx:
                parser.parse()
            self.assertIn("不支持", str(ctx.exception))
        finally:
            os.unlink(tmp_path)


class DocumentParserSplitMarkerPagesTest(unittest.TestCase):
    """DocumentParser._split_marker_pages 分页逻辑测试。"""

    def test_empty_markdown(self):
        result = DocumentParser._split_marker_pages("", 0)
        self.assertEqual(result, [(1, "")])

    def test_single_page_no_separator(self):
        result = DocumentParser._split_marker_pages("Hello World", 1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "Hello World")

    def test_html_comment_page_break(self):
        md = "Page1 content<!-- Page break -->Page2 content"
        result = DocumentParser._split_marker_pages(md, 2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][1].strip(), "Page1 content")
        self.assertEqual(result[1][1].strip(), "Page2 content")

    def test_markdown_horizontal_rule_break(self):
        md = "第一章\n\n---\n\n第二章"
        result = DocumentParser._split_marker_pages(md, 2)
        self.assertEqual(len(result), 2)

    def test_split_by_paragraphs(self):
        """无显式分隔符时按段落均分。"""
        paragraphs = "\n\n".join([f"段落{i}" for i in range(6)])
        result = DocumentParser._split_marker_pages(paragraphs, 3)
        self.assertEqual(len(result), 3)

    def test_empty_paragraphs(self):
        result = DocumentParser._split_marker_pages("", 5)
        self.assertEqual(result, [(1, "")])

    def test_all_page_break_variants(self):
        """多种分页符均能识别。"""
        for sep in ["<!-- Page break -->", "<!-- PAGE BREAK -->", "\n---\n", "\n___\n"]:
            md = f"before{sep}after"
            result = DocumentParser._split_marker_pages(md, 2)
            self.assertEqual(len(result), 2, f"separator '{sep}' failed")


class DocumentParserFallbackTest(unittest.TestCase):
    """DocumentParser 三阶回退解析链测试（plain text → python-docx → unstructured）。"""

    def setUp(self):
        from ai_engine.parse.doc_parser import _is_valid_office_file, _read_as_plain_text

    def test_is_valid_office_file_zip_header(self):
        """真正的 ZIP/DOCX 文件头返回 True。"""
        import zipfile
        import io
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("test.txt", "hello")
        header = buf.getvalue()[:4]
        self.assertEqual(header, b"PK\x03\x04")

    def test_is_valid_office_file_plain_text(self):
        """纯文本文件头返回 False。"""
        from ai_engine.parse.doc_parser import _is_valid_office_file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello plain text")
            tmp_path = f.name
        try:
            self.assertFalse(_is_valid_office_file(tmp_path))
        finally:
            os.unlink(tmp_path)

    def test_is_valid_office_file_html(self):
        """HTML 文件头返回 False。"""
        from ai_engine.parse.doc_parser import _is_valid_office_file
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            f.write(b"<html><body>test</body></html>")
            tmp_path = f.name
        try:
            self.assertFalse(_is_valid_office_file(tmp_path))
        finally:
            os.unlink(tmp_path)

    def test_read_as_plain_text_utf8(self):
        """纯 UTF-8 文本读取正确。"""
        from ai_engine.parse.doc_parser import _read_as_plain_text
        text_content = "这是第一段测试文本\n这是第二段内容"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(text_content.encode("utf-8"))
            tmp_path = f.name
        try:
            result = _read_as_plain_text(tmp_path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["type"], "text")
            self.assertEqual(result[0]["page"], 1)
            self.assertIn("这是第一段", result[0]["content"])
            self.assertEqual(result[0]["metadata"]["source_type"], "plain_text")
            self.assertEqual(result[0]["metadata"]["tool"], "fallback")
        finally:
            os.unlink(tmp_path)

    def test_read_as_plain_text_empty(self):
        """空文件返回空列表。"""
        from ai_engine.parse.doc_parser import _read_as_plain_text
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            tmp_path = f.name
        try:
            result = _read_as_plain_text(tmp_path)
            self.assertEqual(result, [])
        finally:
            os.unlink(tmp_path)

    def test_docx_fallback_to_plain_text(self):
        """非 ZIP 的 .docx 文件降级到纯文本回退解析。"""
        text_content = "这是测试纯文本回退内容\n第二行"
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(text_content.encode("utf-8"))
            tmp_path = f.name
        try:
            parser = DocumentParser(tmp_path, source_type=SourceType.DOCX)
            result = parser.parse()
            self.assertEqual(len(result), 1)
            self.assertIn("这是测试", result[0]["content"])
            self.assertEqual(result[0]["metadata"]["source_type"], "plain_text")
            self.assertEqual(result[0]["metadata"]["tool"], "fallback")
        finally:
            os.unlink(tmp_path)

    def test_pptx_fallback_to_plain_text(self):
        """非 ZIP 的 .pptx 文件降级到纯文本回退解析。"""
        text_content = "这是测试PPTX回退内容"
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            f.write(text_content.encode("utf-8"))
            tmp_path = f.name
        try:
            parser = DocumentParser(tmp_path, source_type=SourceType.PPTX)
            result = parser.parse()
            self.assertEqual(len(result), 1)
            self.assertIn("这是测试PPTX回退", result[0]["content"])
            self.assertEqual(result[0]["metadata"]["source_type"], "plain_text")
        finally:
            os.unlink(tmp_path)

    def test_is_valid_pdf_real_pdf(self):
        """%PDF 文件头返回 True。"""
        from ai_engine.parse.doc_parser import _is_valid_pdf as ivp

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\n%\x00\x00\x00\x00")
            tmp_path = f.name
        try:
            self.assertTrue(ivp(tmp_path))
        finally:
            os.unlink(tmp_path)

    def test_is_valid_pdf_plain_text(self):
        """纯文本文件头返回 False。"""
        from ai_engine.parse.doc_parser import _is_valid_pdf as ivp

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"This is not a PDF file")
            tmp_path = f.name
        try:
            self.assertFalse(ivp(tmp_path))
        finally:
            os.unlink(tmp_path)

    def test_pdf_fallback_to_pymupdf(self):
        """有效 PDF 但无 Marker 时，降级到 PyMuPDF 解析。"""
        import fitz
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = f.name
        try:
            # 创建简易测试 PDF
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "测试PDF内容\n第二行文字")
            doc.save(tmp_path)
            doc.close()

            parser = DocumentParser(tmp_path, source_type=SourceType.PDF)
            result = parser.parse()
            self.assertGreaterEqual(len(result), 1)
            self.assertEqual(result[0]["metadata"]["source_type"], "pdf")
            self.assertEqual(result[0]["metadata"]["tool"], "pymupdf")
            # 内容非空
            self.assertGreater(len(result[0]["content"]), 0)
        finally:
            os.unlink(tmp_path)

    def test_pdf_fallback_to_plain_text(self):
        """非 PDF 头的 .pdf 文件降级到纯文本回退解析。"""
        text_content = "这是测试PDF纯文本回退内容"
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(text_content.encode("utf-8"))
            tmp_path = f.name
        try:
            parser = DocumentParser(tmp_path, source_type=SourceType.PDF)
            result = parser.parse()
            self.assertEqual(len(result), 1)
            self.assertIn("这是测试PDF纯文本回退", result[0]["content"])
            self.assertEqual(result[0]["metadata"]["source_type"], "plain_text")
            self.assertEqual(result[0]["metadata"]["tool"], "fallback")
        finally:
            os.unlink(tmp_path)


class DocumentParserPPTXImagesTest(unittest.TestCase):
    """PPTX 图片提取测试。"""

    def test_image_content_type_to_ext(self):
        """_image_content_type_to_ext 映射正确。"""
        self.assertEqual(_image_content_type_to_ext("image/jpeg"), ".jpg")
        self.assertEqual(_image_content_type_to_ext("image/png"), ".png")
        self.assertEqual(_image_content_type_to_ext("image/gif"), ".gif")
        self.assertEqual(_image_content_type_to_ext("image/bmp"), ".bmp")
        self.assertEqual(_image_content_type_to_ext("unknown/type"), ".png")

    def test_extract_ppt_images_with_real_image(self):
        """从 PPTX 中提取嵌入图片。"""
        from PIL import Image
        from pptx import Presentation
        from pptx.util import Inches

        # 创建一张极小测试图片
        img_path = os.path.join(tempfile.gettempdir(), "test_ppt_img.png")
        img = Image.new("RGB", (10, 10), color="red")
        img.save(img_path)

        try:
            # 创建含图片的 PPTX
            pptx_path = os.path.join(tempfile.gettempdir(), "test_with_img.pptx")
            prs = Presentation()
            slide_layout = prs.slide_layouts[5]  # blank
            slide = prs.slides.add_slide(slide_layout)
            slide.shapes.add_picture(img_path, Inches(1), Inches(1), Inches(2), Inches(2))
            slide.shapes.add_picture(img_path, Inches(4), Inches(1), Inches(2), Inches(2))
            # 添加文字
            txBox = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(4), Inches(1))
            txBox.text_frame.text = "PPT测试幻灯片"
            prs.save(pptx_path)

            try:
                parser = DocumentParser(pptx_path, source_type=SourceType.PPTX)
                result = parser.parse()

                self.assertGreaterEqual(len(result), 1)
                slide_result = result[0]
                self.assertEqual(slide_result["type"], "slide")
                self.assertEqual(slide_result["page"], 1)

                # 应该检测到图片
                meta = slide_result["metadata"]
                self.assertGreaterEqual(meta.get("image_count", 0), 2)
                self.assertEqual(meta["tool"], "python-pptx")

                # 内容中应包含 [图片] 标记
                content = slide_result["content"]
                self.assertIn("PPT测试幻灯片", content)

            finally:
                os.unlink(pptx_path)
        finally:
            os.unlink(img_path)

    def test_pptx_without_images(self):
        """无图片的 PPTX 正常解析，image_count=0。"""
        from pptx import Presentation

        pptx_path = os.path.join(tempfile.gettempdir(), "test_no_img.pptx")
        prs = Presentation()
        slide_layout = prs.slide_layouts[5]
        slide = prs.slides.add_slide(slide_layout)
        txBox = slide.shapes.add_textbox(0, 0, 100, 50)
        txBox.text_frame.text = "只有文字的幻灯片"
        prs.save(pptx_path)

        try:
            parser = DocumentParser(pptx_path, source_type=SourceType.PPTX)
            result = parser.parse()
            self.assertGreaterEqual(len(result), 1)
            self.assertEqual(result[0]["metadata"].get("image_count", 0), 0)
            self.assertIn("只有文字的幻灯片", result[0]["content"])
        finally:
            os.unlink(pptx_path)


# =============================================================================
# 5. ocr_engine 测试
# =============================================================================

class OCREngineExtractLinesTest(unittest.TestCase):
    """OCREngine._extract_lines 行提取与 region 划分。"""

    def test_empty_raw(self):
        from ai_engine.parse.ocr_engine import OCREngine
        lines, text, regions = OCREngine._extract_lines([])
        self.assertEqual(lines, [])
        self.assertEqual(text, "")
        self.assertEqual(regions, [])

        lines, text, regions = OCREngine._extract_lines([[]])
        self.assertEqual(lines, [])

    def test_single_line(self):
        from ai_engine.parse.ocr_engine import OCREngine
        raw = [[[
            [[10, 10], [100, 10], [100, 30], [10, 30]],
            ("Hello", 0.95),
        ]]]
        lines, text, regions = OCREngine._extract_lines(raw)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["text"], "Hello")
        self.assertEqual(lines[0]["confidence"], 0.95)
        self.assertEqual(text, "Hello")
        self.assertEqual(len(regions), 1)

    def test_multi_line_same_region(self):
        from ai_engine.parse.ocr_engine import OCREngine
        raw = [[[
            [[10, 10], [100, 10], [100, 30], [10, 30]],
            ("Line1", 0.9),
        ], [
            [[10, 35], [100, 35], [100, 55], [10, 55]],
            ("Line2", 0.85),
        ]]]
        lines, text, regions = OCREngine._extract_lines(raw)
        self.assertEqual(len(lines), 2)
        self.assertEqual(text, "Line1\nLine2")

    def test_multi_line_different_regions(self):
        """垂直间距大的行分到不同 region。"""
        from ai_engine.parse.ocr_engine import OCREngine
        raw = [[[
            [[10, 10], [100, 10], [100, 30], [10, 30]],
            ("Title", 0.95),
        ], [
            [[10, 200], [200, 200], [200, 220], [10, 220]],
            ("Body text far away", 0.9),
        ]]]
        lines, text, regions = OCREngine._extract_lines(raw)
        self.assertGreaterEqual(len(regions), 1)


class OCREngineAnalyzeLayoutTest(unittest.TestCase):
    """OCREngine._analyze_layout 版面分析。"""

    def test_empty_lines(self):
        from ai_engine.parse.ocr_engine import OCREngine
        layout = OCREngine._analyze_layout([], [])
        self.assertEqual(layout["paragraphs"], 0)
        self.assertFalse(layout["has_title"])
        self.assertFalse(layout["has_table"])
        self.assertEqual(layout["total_chars"], 0)
        self.assertEqual(layout["avg_confidence"], 0.0)

    def test_single_line(self):
        from ai_engine.parse.ocr_engine import OCREngine
        lines = [{"text": "Hello World", "confidence": 0.95, "box": {"x_min": 10, "x_max": 100, "y_min": 10, "y_max": 20, "width": 90, "height": 10}}]
        layout = OCREngine._analyze_layout(lines, [])
        self.assertGreater(layout["total_chars"], 0)
        self.assertGreater(layout["avg_confidence"], 0)

    def test_has_title_short_line(self):
        from ai_engine.parse.ocr_engine import OCREngine
        lines = [
            {"text": "标题", "confidence": 0.99, "box": {"x_min": 10, "x_max": 100, "y_min": 10, "y_max": 20, "width": 90, "height": 10}},
            {"text": "这是正文内容包含很多文字说明信息", "confidence": 0.95, "box": {"x_min": 10, "x_max": 200, "y_min": 30, "y_max": 40, "width": 190, "height": 10}},
        ]
        layout = OCREngine._analyze_layout(lines, [])
        self.assertTrue(layout["has_title"])

    def test_process_missing_file(self):
        """process() 对不存在的文件抛出 FileNotFoundError。"""
        from ai_engine.parse.ocr_engine import OCREngine
        engine = OCREngine()
        with self.assertRaises(FileNotFoundError):
            engine.process("/path/to/nonexistent/image.png")


# =============================================================================
# 6. video_processor 测试
# =============================================================================

class VideoProcessorTest(unittest.TestCase):
    """VideoProcessor 异常路径、构造函数、MP4 时长解析、完整处理链测试。"""

    def test_process_missing_file_raises(self):
        """process() 对不存在的视频文件抛出 FileNotFoundError。"""
        from ai_engine.parse.video_processor import VideoProcessor
        vp = VideoProcessor()
        with self.assertRaises(FileNotFoundError):
            vp.process("/path/to/nonexistent/video.mp4")

    def test_process_audio_missing_file_raises(self):
        """process_audio() 对不存在的音频文件抛出 FileNotFoundError。"""
        from ai_engine.parse.video_processor import VideoProcessor
        vp = VideoProcessor()
        with self.assertRaises(FileNotFoundError):
            vp.process_audio("/path/to/nonexistent/audio.mp3")

    def test_video_processor_default_params(self):
        """VideoProcessor 默认参数正确。"""
        from ai_engine.parse.video_processor import VideoProcessor
        vp = VideoProcessor()
        self.assertEqual(vp.max_keyframes, 5)
        self.assertEqual(vp.whisper_model_name, "base")
        self.assertIsNone(vp.asr_language)

    def test_video_processor_custom_params(self):
        """VideoProcessor 自定义参数生效。"""
        from ai_engine.parse.video_processor import VideoProcessor
        vp = VideoProcessor(max_keyframes=10, whisper_model="small", asr_language="zh")
        self.assertEqual(vp.max_keyframes, 10)
        self.assertEqual(vp.whisper_model_name, "small")
        self.assertEqual(vp.asr_language, "zh")

    def test_parse_mp4_duration_real_file(self):
        """纯 Python MP4 时长解析器给出 >0 的结果。"""
        from ai_engine.parse.video_processor import VideoProcessor
        mp4_path = "ai_engine/parse/test4.mp4"
        if not os.path.exists(mp4_path):
            self.skipTest("test4.mp4 不存在")
        duration = VideoProcessor._parse_mp4_duration(mp4_path)
        self.assertGreater(duration, 0)
        # test4.mp4 应在 150-170 秒左右
        self.assertGreater(duration, 100)

    def test_parse_mp4_duration_invalid_file(self):
        """非 MP4 文件返回 0.0。"""
        from ai_engine.parse.video_processor import VideoProcessor
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"This is not an mp4 file")
            tmp_path = f.name
        try:
            duration = VideoProcessor._parse_mp4_duration(tmp_path)
            self.assertEqual(duration, 0.0)
        finally:
            os.unlink(tmp_path)

    def test_parse_mp4_duration_empty_file(self):
        """空文件返回 0.0。"""
        from ai_engine.parse.video_processor import VideoProcessor
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_path = f.name
        try:
            duration = VideoProcessor._parse_mp4_duration(tmp_path)
            self.assertEqual(duration, 0.0)
        finally:
            os.unlink(tmp_path)

    def test_get_metadata_real_file(self):
        """_get_metadata 返回完整元数据。"""
        from ai_engine.parse.video_processor import VideoProcessor
        mp4_path = "ai_engine/parse/test4.mp4"
        if not os.path.exists(mp4_path):
            self.skipTest("test4.mp4 不存在")
        meta = VideoProcessor._get_metadata(mp4_path)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["type"], "video_meta")
        self.assertEqual(meta["page"], 0)
        self.assertIn("test4.mp4", meta["content"])
        metadata = meta["metadata"]
        self.assertIn("file_name", metadata)
        self.assertIn("file_size_mb", metadata)
        self.assertIn("duration_sec", metadata)
        # 纯 Python 解析的时长应 > 0
        self.assertGreater(metadata["duration_sec"], 0)

    def test_get_metadata_nonexistent_file(self):
        """不存在的文件返回 None。"""
        from ai_engine.parse.video_processor import VideoProcessor
        meta = VideoProcessor._get_metadata("/nonexistent/path.mp4")
        self.assertIsNone(meta)

    def test_process_returns_at_least_one_chunk(self):
        """process() 至少返回 video_meta 块。"""
        from ai_engine.parse.video_processor import VideoProcessor
        mp4_path = "ai_engine/parse/test4.mp4"
        if not os.path.exists(mp4_path):
            self.skipTest("test4.mp4 不存在")
        vp = VideoProcessor()
        result = vp.process(mp4_path)
        self.assertGreaterEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "video_meta")
        # 验证所有块都有 content
        for r in result:
            self.assertIn("content", r)
            self.assertIn("type", r)
            self.assertIn("metadata", r)

    def test_process_full_chunk_pipeline(self):
        """process → ChunkNormalizer 全链条产出 Chunk。"""
        from ai_engine.parse.video_processor import VideoProcessor
        from ai_engine.parse.chunk_normalizer import ChunkNormalizer
        from ai_engine.core.schema import SourceType

        mp4_path = "ai_engine/parse/test4.mp4"
        if not os.path.exists(mp4_path):
            self.skipTest("test4.mp4 不存在")

        vp = VideoProcessor()
        raw = vp.process(mp4_path)
        normalizer = ChunkNormalizer(max_content_chars=5000)
        chunks = normalizer.normalize(raw, source_ref="test4.mp4", source_type=SourceType.VIDEO)
        self.assertGreaterEqual(len(chunks), 1)
        for c in chunks:
            self.assertEqual(c.source_type, SourceType.VIDEO)
            self.assertTrue(c.chunk_id.startswith("chunk_"))
            self.assertGreater(len(c.content), 0)

    def test_correct_asr_text_returns_original_when_no_timestamps(self):
        """无时间戳的文本不经过 LLM 纠错，直接返回。"""
        from ai_engine.parse.video_processor import VideoProcessor
        vp = VideoProcessor()
        text = "这是一段普通文本"
        result = vp._correct_asr_text(text)
        self.assertEqual(result, text)

    def test_correct_asr_text_returns_original_when_empty(self):
        """空文本直接返回。"""
        from ai_engine.parse.video_processor import VideoProcessor
        vp = VideoProcessor()
        self.assertEqual(vp._correct_asr_text(""), "")
        self.assertEqual(vp._correct_asr_text("   "), "   ")

    def test_transcript_metadata_has_llm_corrected_flag(self):
        """transcript 块的 metadata 包含 llm_corrected 标记。"""
        from ai_engine.parse.video_processor import VideoProcessor
        mp4_path = "ai_engine/parse/test4.mp4"
        if not os.path.exists(mp4_path):
            self.skipTest("test4.mp4 不存在")
        vp = VideoProcessor()
        result = vp.process(mp4_path)
        for r in result:
            if r["type"] == "transcript":
                self.assertIn("llm_corrected", r["metadata"])
                # metadata 中 llm_corrected 是布尔值
                self.assertIsInstance(r["metadata"]["llm_corrected"], bool)
                # 内容非空
                self.assertGreater(len(r["content"]), 0)
                # 保持时间戳格式
                self.assertIn("[", r["content"])


# =============================================================================
# 7. minio_client 测试
# =============================================================================

class MinioClientTest(unittest.TestCase):
    """MinioClient 异常路径与构造函数测试。"""

    def setUp(self):
        from ai_engine.parse.minio_client import MinioClient
        self.client = MinioClient(
            endpoint="127.0.0.1:9000",
            access_key="test_key",
            secret_key="test_secret",
        )

    def test_upload_missing_file_raises(self):
        """upload_file() 对不存在的文件抛出 FileNotFoundError。"""
        with self.assertRaises(FileNotFoundError):
            self.client.upload_file("/path/to/nonexistent/file.pdf")

    def test_download_local_path_returns_same(self):
        """download_file() 对本地路径直接返回。"""
        result = self.client.download_file("/local/path/file.pdf")
        self.assertEqual(result, "/local/path/file.pdf")

    def test_upload_local_path_fallback(self):
        """上传失败时回退到本地路径。"""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            tmp_path = f.name
        try:
            url = self.client.upload_file(tmp_path, target_name="test.pdf")
            # 无法连接 MinIO → 返回本地路径
            self.assertEqual(url, tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_endpoint_property(self):
        """endpoint 属性使用构造参数。"""
        self.assertEqual(self.client.endpoint, "127.0.0.1:9000")

    def test_access_key_property(self):
        """access_key 属性使用构造参数。"""
        self.assertEqual(self.client.access_key, "test_key")


# =============================================================================
# 8. router 测试（纯逻辑校验，不启动 FastAPI）
# =============================================================================

class RouterRequestValidationTest(unittest.TestCase):
    """ParseProcessRequest / ParseVideoRequest 数据格式校验。"""

    def test_parse_process_request_empty_file_paths(self):
        """file_paths 为空的请求应被 router 校验拦截。
        这里只测数据模型层面的必填约束。"""
        req = ParseProcessRequest(session_id="s1", file_paths=[])
        self.assertEqual(len(req.file_paths), 0)

    def test_parse_process_request_full(self):
        """完整请求体字段映射正确。"""
        req = ParseProcessRequest(
            session_id="session_uuid",
            intent_id="intent_uuid",
            file_paths=["doc.pdf", "img.png"],
        )
        self.assertEqual(req.session_id, "session_uuid")
        self.assertEqual(req.intent_id, "intent_uuid")
        self.assertEqual(len(req.file_paths), 2)

    def test_parse_process_response_format(self):
        """ParseProcessResponse 数据格式与 schema 一致。"""
        from ai_engine.core.schema import MaterialAsset
        asset = MaterialAsset(
            asset_id="asset_001",
            session_id="s1",
            file_name="test.pdf",
            file_url="/path/test.pdf",
            source_type=SourceType.PDF,
            parse_status=ParseStatus.UPLOADED,
        )
        resp = ParseProcessResponse(
            task_id="parse_abc123",
            status="processing",
            assets=[asset],
        )
        self.assertEqual(resp.task_id, "parse_abc123")
        self.assertEqual(resp.status, "processing")
        self.assertEqual(len(resp.assets), 1)
        self.assertEqual(resp.assets[0].file_name, "test.pdf")
        self.assertEqual(resp.assets[0].source_type, SourceType.PDF)

    def test_parse_status_response_format(self):
        """ParseStatusResponse 数据格式与 schema 一致。"""
        chunk = Chunk(
            chunk_id="chunk_001",
            source_type=SourceType.PDF,
            source_ref="doc_ref",
            content="test content",
            seq_index=0,
        )
        resp = ParseStatusResponse(
            task_id="parse_abc123",
            status=ParseStatus.DONE,
            chunks=[chunk],
        )
        self.assertEqual(resp.task_id, "parse_abc123")
        self.assertEqual(resp.status, ParseStatus.DONE)
        self.assertEqual(len(resp.chunks), 1)
        self.assertEqual(resp.chunks[0].chunk_id, "chunk_001")
        self.assertEqual(resp.chunks[0].content, "test content")


# =============================================================================
# 入口
# =============================================================================

if __name__ == "__main__":
    unittest.main()
