import importlib
import math
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_engine.core.llm import LLMClient


class _FakeEmbedder:
    def __init__(self, vectors):
        self.vectors = vectors

    def encode(self, texts, normalize_embeddings=True):
        return self.vectors[:len(texts)]


class TestLocalEmbeddingValidation(unittest.TestCase):
    def setUp(self):
        import ai_engine.core.llm as llm_module
        self.llm_module = llm_module
        self.previous = getattr(llm_module, "_local_embedder", None)
        llm_module.__dict__.pop("_local_embedder", None)
        self.model_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "AI_GEN_MODE": "llm",
                "AI_EMBEDDING_MODEL_PATH": self.model_dir.name,
                "AI_EMBEDDING_DIM": "3",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.model_dir.cleanup()
        self.llm_module.__dict__.pop("_local_embedder", None)
        if self.previous is not None:
            self.llm_module._local_embedder = self.previous

    def test_accepts_nonzero_vectors_with_expected_dimension(self):
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=_FakeEmbedder([[1.0, 0.0, 0.5]]),
        ) as constructor:
            vectors = LLMClient().embed(["text"])
        constructor.assert_called_once_with(
            self.model_dir.name, device="cpu", local_files_only=True
        )
        self.assertEqual(vectors, [[1.0, 0.0, 0.5]])

    def test_rejects_wrong_dimension(self):
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=_FakeEmbedder([[1.0, 0.0]]),
        ):
            with self.assertRaisesRegex(RuntimeError, "维度错误"):
                LLMClient().embed(["text"])

    def test_rejects_zero_vector(self):
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=_FakeEmbedder([[0.0, 0.0, 0.0]]),
        ):
            with self.assertRaisesRegex(RuntimeError, "零向量"):
                LLMClient().embed(["text"])

    def test_rejects_non_finite_vectors(self):
        for invalid in (math.nan, math.inf, -math.inf):
            self.llm_module.__dict__.pop("_local_embedder", None)
            with self.subTest(invalid=invalid), patch(
                "sentence_transformers.SentenceTransformer",
                return_value=_FakeEmbedder([[1.0, invalid, 0.5]]),
            ):
                with self.assertRaisesRegex(RuntimeError, "非有限数值"):
                    LLMClient().embed(["text"])

    def test_rejects_non_finite_norm(self):
        with patch(
            "sentence_transformers.SentenceTransformer",
            return_value=_FakeEmbedder([[1.7e308, 1.7e308, 1.7e308]]),
        ):
            with self.assertRaisesRegex(RuntimeError, "向量范数无效"):
                LLMClient().embed(["text"])

    def test_missing_model_directory_does_not_load(self):
        with patch.dict(
            os.environ,
            {"AI_EMBEDDING_MODEL_PATH": os.path.join(self.model_dir.name, "missing")},
        ), patch("sentence_transformers.SentenceTransformer") as constructor:
            with self.assertRaisesRegex(RuntimeError, "模型目录不存在"):
                LLMClient().embed(["text"])
        constructor.assert_not_called()

    def test_model_load_failure_is_not_silent(self):
        with patch(
            "sentence_transformers.SentenceTransformer",
            side_effect=OSError("model unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "本地Embedding失败"):
                LLMClient().embed(["text"])

    def test_upload_does_not_report_success_when_embedding_fails(self):
        from ai_engine.main import app

        rag_router = importlib.import_module("ai_engine.rag.router")
        with (
            patch.object(
                rag_router._embed_service,
                "embed_chunks",
                side_effect=RuntimeError("model unavailable"),
            ),
            patch.object(rag_router._store, "insert_batch") as insert_batch,
        ):
            response = TestClient(app).post(
                "/api/v1/knowledge/upload",
                json={"texts": ["BGE failure regression fixture"]},
            )

        self.assertEqual(response.status_code, 500)
        self.assertIn("知识库索引失败", response.json()["detail"])
        insert_batch.assert_not_called()


class TestEmbeddingDefaults(unittest.TestCase):
    def test_embedding_and_store_default_to_512(self):
        from ai_engine.rag.embed import EmbeddingService
        from ai_engine.rag.store_pgvector import PGVectorStore

        with patch.dict(os.environ, {"AI_GEN_MODE": "mock"}, clear=True):
            self.assertEqual(EmbeddingService().dim, 512)
            self.assertEqual(PGVectorStore(conn_string="postgresql://unused").embedding_dim, 512)
