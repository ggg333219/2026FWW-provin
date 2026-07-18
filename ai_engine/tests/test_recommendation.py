import unittest

from ai_engine.recommendation.schemas import RequestDTO, ResourceType, StageType
from ai_engine.recommendation.service import RecommendationEngine


class AlwaysHealthyCache:
    async def get(self, url: str):
        return True

    async def set(self, url: str, status: bool):
        return None


class RecommendationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_recommendation_flow(self):
        engine = RecommendationEngine(
            url_cache=AlwaysHealthyCache(),
            reason_provider=lambda req, res: f"命中{req.knowledge_point or req.keyword}，可直接用于课堂导入。",
            top_k=3,
        )
        request = RequestDTO(
            keyword="函数",
            target_goal="帮助学生掌握函数图像与单调性",
            knowledge_point="函数单调性",
            stage=StageType.HIGH,
            type=ResourceType.WEB_COURSE,
            difficulty=0.4,
            duration=30,
            budget=20,
            source_preference=["web_video"],
        )

        result = await engine.recommend_with_fallback(request)

        self.assertIn("intent", result)
        self.assertIn("recommended_resources", result)
        self.assertIn("resources", result)
        self.assertGreaterEqual(result["returned"], 1)
        first = result["recommended_resources"][0]
        self.assertIn("title", first)
        self.assertIn("score", first)
        self.assertIn("fit_reason", first)
        self.assertIn("reason", first)

    async def test_adapter_fallback(self):
        def broken_reason_provider(req, res):
            raise TimeoutError("ai timeout")

        engine = RecommendationEngine(
            url_cache=AlwaysHealthyCache(),
            reason_provider=broken_reason_provider,
            top_k=3,
        )
        request = RequestDTO(
            keyword="函数",
            target_goal="复习函数基础",
            knowledge_point="定义域",
            stage=StageType.HIGH,
            type=ResourceType.WEB_COURSE,
            difficulty=0.3,
            duration=25,
            budget=0,
        )

        result = await engine.recommend_with_fallback(request)

        self.assertTrue(result["fallback_used"])
        self.assertGreaterEqual(result["returned"], 1)
        self.assertIn("recommended_resources", result)
        self.assertGreaterEqual(len(result["recommended_resources"]), 1)
        for item in result["recommended_resources"]:
            self.assertTrue(item["fit_reason"])


if __name__ == "__main__":
    unittest.main()
