from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from fastapi import APIRouter, FastAPI, HTTPException

try:
    from ..recommender import get_recommendations
except ImportError:
    from recommender import get_recommendations
from .adapters import BaseSourceAdapter, LocalDBAdapter, WebVideoAdapter
from .schemas import FeedbackAckDTO, RequestDTO, ResourceDTO, TeacherFeedbackDTO


@dataclass
class RankingWeights:
    difficulty: float = 0.30
    duration: float = 0.20
    price: float = 0.20
    preference: float = 0.15
    heat: float = 0.15


class URLStatusCache:
    """URL 健康状态缓存，优先 Redis，不可用则自动降级到内存。"""

    def __init__(self, ttl_seconds: int = 1800):
        self.ttl_seconds = ttl_seconds
        self._memory_cache: dict[str, tuple[bool, float]] = {}
        self._redis = None
        self._redis_ready = False

        redis_url = (os.getenv("REDIS_URL") or "").strip()
        if redis_url:
            try:
                import redis.asyncio as redis  # type: ignore

                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis_ready = True
            except Exception:
                self._redis_ready = False

    def _cache_key(self, url: str) -> str:
        digest = hashlib.md5(url.encode("utf-8")).hexdigest()
        return f"url_status:{digest}"

    async def get(self, url: str) -> bool | None:
        key = self._cache_key(url)
        if self._redis_ready and self._redis is not None:
            try:
                value = await self._redis.get(key)
                if value is None:
                    return None
                return value == "1"
            except Exception:
                pass

        value = self._memory_cache.get(key)
        if not value:
            return None
        status, expire_at = value
        if time.time() > expire_at:
            self._memory_cache.pop(key, None)
            return None
        return status

    async def set(self, url: str, status: bool):
        key = self._cache_key(url)
        if self._redis_ready and self._redis is not None:
            try:
                await self._redis.set(key, "1" if status else "0", ex=self.ttl_seconds)
                return
            except Exception:
                pass

        self._memory_cache[key] = (status, time.time() + self.ttl_seconds)


class FeedbackRepository:
    """最小可用反馈存储，默认落地 sqlite，便于本地和测试环境直接运行。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(Path("uploads") / "recommendation_feedback.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_table()

    def _init_table(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS teacher_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teacher_id TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def insert_feedback(self, payload: TeacherFeedbackDTO):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO teacher_feedback (teacher_id, resource_id, action, ts) VALUES (?, ?, ?, ?)",
                (
                    payload.teacher_id,
                    payload.resource_id,
                    payload.action.value,
                    payload.timestamp.astimezone(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


class ResourceRecommendAgent:
    def __init__(
        self,
        adapters: list[BaseSourceAdapter] | None = None,
        url_cache: URLStatusCache | None = None,
        reason_provider: Callable[[RequestDTO, ResourceDTO], str] | None = None,
        ranking_weights: RankingWeights | None = None,
        top_k: int = 5,
    ):
        self.adapters = adapters or [LocalDBAdapter(), WebVideoAdapter()]
        self.url_cache = url_cache or URLStatusCache()
        self.reason_provider = reason_provider
        self.ranking_weights = ranking_weights or RankingWeights()
        self.top_k = top_k

    @staticmethod
    def _extract_json_payload(text: str) -> dict:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json\n", "", 1).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("模型返回内容中未找到有效 JSON")
        return json.loads(cleaned[start : end + 1])

    def _build_ai_recommendation_prompt(self, request: RequestDTO, intent: list[str]) -> tuple[str, str]:
        system_prompt = (
            "你是智能教研平台的资源推荐助手。"
            "你必须只输出 JSON，不要输出解释文本、Markdown 或代码块。"
            "无论上下文是否完整，都必须返回至少 3 个资源。"
            "如果找不到本地匹配资源，绝对不能返回空列表；"
            "必须基于你的知识库与常识，推荐 B 站、51教习、知乎、国家中小学智慧教育平台等真实可访问的网课入口。"
            "如果无法精确得知资源 URL，请预测性生成可点击的搜索结果链接或首页链接。"
            "视频讲解优先指向 B 站搜索结果页，课件、题单、试题类内容优先指向 51教习搜索结果页。"
            "最终 JSON 的根键名必须是 recommended_resources。"
            "recommended_resources 的每一项都必须包含字段：title,type,source,url,fit_reason。"
            "你可以额外补充 summary、tags、duration、price、score，但不要遗漏上述字段。"
            "如果无法召回真实资源，也要基于常识生成高质量的学习资源推荐。"
        )
        user_prompt = (
            f"keyword={request.keyword}\n"
            f"target_goal={request.target_goal}\n"
            f"knowledge_point={request.knowledge_point}\n"
            f"subject={request.subject}\n"
            f"stage={request.stage.value if hasattr(request.stage, 'value') else request.stage}\n"
            f"type={request.type.value if hasattr(request.type, 'value') else request.type}\n"
            f"difficulty={request.difficulty}\n"
            f"duration={request.duration}\n"
            f"budget={request.budget}\n"
            f"source_preference={','.join(request.source_preference) if request.source_preference else '无'}\n"
            f"intent={' | '.join(intent)}\n"
            "请直接输出符合要求的 JSON。"
        )
        return system_prompt, user_prompt

    def _normalize_recommended_item(self, item: dict | ResourceDTO, request: RequestDTO) -> dict[str, object]:
        if isinstance(item, ResourceDTO):
            title = item.title
            resource_type = item.type.value if hasattr(item.type, "value") else str(item.type)
            source = item.source
            url = str(item.url)
            fit_reason = item.reason or self._rule_reason(request, item)
            return {
                "title": title,
                "type": resource_type,
                "source": source,
                "url": url,
                "fit_reason": fit_reason,
                "reason": fit_reason,
                "duration": item.duration,
                "score": item.score,
                "summary": item.summary,
                "tags": item.tags,
            }

        resource_item = dict(item or {})
        title = str(resource_item.get("title") or resource_item.get("Title") or "未命名资源").strip()
        resource_type = str(resource_item.get("type") or resource_item.get("Type") or getattr(request.type, "value", request.type)).strip()
        source = str(resource_item.get("source") or resource_item.get("Source") or "ai_generated").strip()
        url = str(resource_item.get("url") or resource_item.get("link") or resource_item.get("Link") or "").strip()
        fit_reason = str(resource_item.get("fit_reason") or resource_item.get("reason") or resource_item.get("recommend_reason") or "匹配当前教学目标").strip()
        if not url:
            url = self._guess_url(title, request)
        return {
            "title": title,
            "type": resource_type,
            "source": source,
            "url": url,
            "fit_reason": fit_reason,
            "reason": fit_reason,
            "duration": resource_item.get("duration", request.duration),
            "score": resource_item.get("score", 0),
            "summary": resource_item.get("summary", ""),
            "tags": resource_item.get("tags", []),
        }

    def _guess_url(self, title: str, request: RequestDTO) -> str:
        keyword = quote_plus(request.knowledge_point or request.keyword or title)
        lower_title = title.lower()
        if "知乎" in title or "zhihu" in lower_title:
            return f"https://www.zhihu.com/search?type=content&q={keyword}"
        if "51教习" in title or "51jiaoxi" in lower_title or "学科网" in title or "zxxk" in lower_title or "xkw" in lower_title:
            return f"https://www.51jiaoxi.com/search?keyword={keyword}"
        if "B站" in title or "b站" in title or "bilibili" in lower_title:
            return f"https://search.bilibili.com/all?keyword={keyword}"
        if "智慧教育" in title or "smartedu" in lower_title or "国家" in title:
            return "https://basic.smartedu.cn/"
        return f"https://search.bilibili.com/all?keyword={keyword}"

    def _build_fallback_resources(self, request: RequestDTO) -> list[dict[str, object]]:
        keyword = (request.knowledge_point or request.keyword or request.target_goal or "教学资源").strip()
        encoded_keyword = quote_plus(keyword)
        stage_label = request.stage.value if hasattr(request.stage, "value") else str(request.stage)
        subject_label = (request.subject or request.knowledge_point or "相关学科").strip()
        resource_type = request.type.value if hasattr(request.type, "value") else request.type

        def fit_reason(platform_name: str) -> str:
            if "选择排序" in keyword:
                return f"面向{stage_label}{subject_label}教学，动态演示清晰，便于讲解选择排序的比较与交换过程。"
            if "排序" in keyword:
                return f"面向{stage_label}{subject_label}教学，适合用可视化方式讲解排序过程与算法思路。"
            return f"面向{stage_label}{subject_label}教学，内容结构清晰，适合课堂导入与知识巩固。"

        resources = [
            {
                "title": f"B站：{keyword} 详解",
                "type": resource_type,
                "source": "bilibili",
                "url": f"https://search.bilibili.com/all?keyword={encoded_keyword}",
                "fit_reason": fit_reason("bilibili"),
            },
            {
                "title": f"51教习：{keyword} 课件与题单",
                "type": resource_type,
                "source": "51jiaoxi",
                "url": f"https://www.51jiaoxi.com/search?keyword={encoded_keyword}",
                "fit_reason": fit_reason("51jiaoxi"),
            },
            {
                "title": f"知乎：{keyword} 教学讲解",
                "type": resource_type,
                "source": "zhihu",
                "url": f"https://www.zhihu.com/search?type=content&q={encoded_keyword}",
                "fit_reason": fit_reason("zhihu"),
            },
            {
                "title": f"国家中小学智慧教育平台：{keyword}",
                "type": resource_type,
                "source": "smartedu",
                "url": "https://basic.smartedu.cn/",
                "fit_reason": fit_reason("smartedu"),
            },
        ]
        return [
            {
                **item,
                "duration": max(10, min(request.duration or 30, 60)),
                "score": 0.8 - idx * 0.05,
                "summary": item["fit_reason"],
                "tags": [keyword, stage_label, subject_label, item["source"]],
                "price": 0.0,
            }
            for idx, item in enumerate(resources)
        ]

    def _call_ai_recommendations(self, request: RequestDTO, intent: list[str]) -> list[dict[str, object]]:
        fallback_resources = self._build_fallback_resources(request)
        try:
            from openai import OpenAI
        except ImportError:
            return fallback_resources

        api_key = (os.getenv("AI_API_KEY") or "").strip()
        if not api_key:
            return fallback_resources

        system_prompt, user_prompt = self._build_ai_recommendation_prompt(request, intent)
        model = os.getenv("AI_MODEL", "gpt-4o-mini")
        client = OpenAI(api_key=api_key, base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1"))

        response = client.chat.completions.create(
            model=model,
            temperature=0.7,
            timeout=12,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        print(f"[ResourceRecommendAgent] raw_ai_response={content}", flush=True)
        try:
            payload = self._extract_json_payload(content)
            items = payload.get("recommended_resources")
            if not isinstance(items, list):
                items = payload.get("resources")
            if not isinstance(items, list):
                return fallback_resources

            normalized = [self._normalize_recommended_item(item, request) for item in items if isinstance(item, (dict, ResourceDTO))]
            if len(normalized) < 3:
                normalized.extend(fallback_resources[len(normalized):3])
            return normalized[: self.top_k] or fallback_resources
        except Exception:
            return fallback_resources

    def parse_intent(self, request: RequestDTO) -> list[str]:
        merged = " ".join([request.keyword, request.target_goal, request.knowledge_point]).strip().lower()
        words = [w for w in re.split(r"[\s,，。；;、/]+", merged) if w]
        words.extend([request.stage.value.lower(), request.type.value.lower()])
        # 去重并保留顺序
        seen: set[str] = set()
        ordered: list[str] = []
        for word in words:
            if word in seen:
                continue
            seen.add(word)
            ordered.append(word)
        return ordered[:12]

    def retrieve_candidates(self, request: RequestDTO, expanded_keywords: list[str]) -> list[ResourceDTO]:
        candidates: list[ResourceDTO] = []
        for adapter in self.adapters:
            if request.source_preference and adapter.source_name not in request.source_preference:
                continue
            candidates.extend(adapter.search(request, expanded_keywords))

        merged: dict[str, ResourceDTO] = {}
        for item in candidates:
            merged[item.resource_id] = item
        return list(merged.values())

    def rerank_resources(self, request: RequestDTO, candidates: list[ResourceDTO]) -> list[ResourceDTO]:
        if not candidates:
            return []

        def closeness(val: float, target: float, scale: float) -> float:
            return max(0.0, 1.0 - (abs(val - target) / max(scale, 1.0)))

        for resource in candidates:
            duration_score = closeness(float(resource.duration), float(request.duration), 60.0)
            difficulty_score = self._difficulty_score(request, resource)
            price_score = 1.0 if resource.price <= request.budget else max(0.0, 1.0 - (resource.price - request.budget) / 100.0)
            pref_score = 1.0 if (not request.source_preference or resource.source in request.source_preference) else 0.2
            heat_score = max(0.0, min(1.0, resource.heat))

            w = self.ranking_weights
            resource.score = (
                w.difficulty * difficulty_score
                + w.duration * duration_score
                + w.price * price_score
                + w.preference * pref_score
                + w.heat * heat_score
            )

        return sorted(candidates, key=lambda item: item.score, reverse=True)

    async def generate_reasons(self, request: RequestDTO, ranked: list[ResourceDTO]) -> tuple[list[ResourceDTO], bool]:
        top3_ids = {item.resource_id for item in ranked[:3]}
        ai_degraded = False

        for item in ranked:
            if item.resource_id not in top3_ids:
                item.reason = "匹配教学目标与课堂条件，建议作为备选资源。"
                continue

            try:
                item.reason = self._ai_reason(request, item)
            except Exception:
                ai_degraded = True
                item.reason = self._rule_reason(request, item)
        return ranked, ai_degraded

    async def validate_urls(self, resources: list[ResourceDTO]) -> list[ResourceDTO]:
        async def validate_one(item: ResourceDTO) -> bool:
            cached = await self.url_cache.get(str(item.url))
            if cached is not None:
                return cached

            def _head_request() -> bool:
                try:
                    req = Request(str(item.url), method="HEAD")
                    with urlopen(req, timeout=3) as resp:
                        return 200 <= int(resp.status) < 400
                except Exception:
                    return False

            ok = await asyncio.to_thread(_head_request)
            await self.url_cache.set(str(item.url), ok)
            return ok

        checks = await asyncio.gather(*[validate_one(item) for item in resources])
        return [item for item, ok in zip(resources, checks) if ok]

    async def recommend(self, request: RequestDTO) -> dict:
        intent = self.parse_intent(request)
        candidates = self.retrieve_candidates(request, intent)

        if not candidates:
            ai_resources = self._call_ai_recommendations(request, intent)
            return self._format_response(
                request=request,
                intent=intent,
                resources=ai_resources,
                total_candidates=0,
                fallback_used=True,
            )

        ranked = self.rerank_resources(request, candidates)
        validated = await self.validate_urls(ranked)
        if not validated:
            validated = ranked[: self.top_k]

        enriched, ai_degraded = await self.generate_reasons(request, validated[: self.top_k])
        return self._format_response(
            request=request,
            intent=intent,
            resources=enriched,
            total_candidates=len(candidates),
            fallback_used=ai_degraded,
        )

    async def recommend_with_fallback(self, request: RequestDTO) -> dict:
        try:
            return await self.recommend(request)
        except Exception:
            return self._fallback_recommend(request)

    def _difficulty_score(self, request: RequestDTO, resource: ResourceDTO) -> float:
        if not resource.tags:
            return 0.6
        easy_tokens = {"基础", "入门", "速通"}
        hard_tokens = {"拔高", "竞赛", "进阶"}
        tag_text = " ".join(resource.tags)
        inferred = 0.5
        if any(token in tag_text for token in easy_tokens):
            inferred = 0.3
        if any(token in tag_text for token in hard_tokens):
            inferred = 0.8
        return max(0.0, 1.0 - abs(inferred - request.difficulty))

    def _ai_reason(self, request: RequestDTO, resource: ResourceDTO) -> str:
        if self.reason_provider is not None:
            return self.reason_provider(request, resource)

        api_key = (os.getenv("AI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("missing_api_key")

        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=os.getenv("AI_BASE_URL", "https://api.openai.com/v1"))
        model = os.getenv("AI_MODEL", "gpt-4o-mini")

        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            timeout=8,
            messages=[
                {
                    "role": "system",
                    "content": "你是教研推荐助手，请用一句话说明该资源为何适合当前教学目标，要求具体可执行。",
                },
                {
                    "role": "user",
                    "content": (
                        f"教学目标: {request.target_goal}\n"
                        f"知识点: {request.knowledge_point}\n"
                        f"资源标题: {resource.title}\n"
                        f"资源摘要: {resource.summary}\n"
                        "请输出一句推荐理由。"
                    ),
                },
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            return self._rule_reason(request, resource)
        return content

    def _rule_reason(self, request: RequestDTO, resource: ResourceDTO) -> str:
        return (
            f"该资源围绕“{request.knowledge_point or request.keyword}”，时长约{resource.duration}分钟，"
            f"价格{resource.price:.1f}元，便于在当前课堂目标下快速使用。"
        )

    def _fallback_recommend(self, request: RequestDTO) -> dict:
        intent = self.parse_intent(request)
        candidates = self.retrieve_candidates(request, intent)

        if not candidates:
            return self._format_response(
                request=request,
                intent=intent,
                resources=self._build_fallback_resources(request),
                total_candidates=0,
                fallback_used=True,
            )

        ranked = self.rerank_resources(request, candidates)
        for item in ranked[: self.top_k]:
            item.reason = self._rule_reason(request, item)

        return self._format_response(
            request=request,
            intent=intent,
            resources=ranked[: self.top_k],
            total_candidates=len(candidates),
            fallback_used=True,
        )

    def _build_fallback_resources_legacy(self, request: RequestDTO) -> list[ResourceDTO]:
        keyword = (request.knowledge_point or request.keyword or request.target_goal or "教学资源").strip()
        encoded_keyword = quote_plus(keyword)
        stage_label = request.stage.value if hasattr(request.stage, "value") else str(request.stage)
        subject_label = request.subject.strip() if isinstance(request.subject, str) else str(request.subject)
        resource_type = request.type if hasattr(request.type, "value") else request.type

        return [
            ResourceDTO(
                resource_id=f"fallback_bilibili_{hashlib.md5(('bilibili:' + keyword).encode('utf-8')).hexdigest()[:10]}",
                title=f"{keyword} - B站检索入口",
                type=resource_type,
                summary=f"面向{stage_label}阶段、{subject_label or '相关学科'}的公开视频检索入口。",
                tags=[keyword, stage_label, subject_label, "bilibili"],
                grade=stage_label,
                subject=subject_label,
                duration=max(10, min(request.duration or 30, 60)),
                price=0.0,
                source="bilibili",
                url=f"https://search.bilibili.com/all?keyword={encoded_keyword}",
                score=0.88,
                reason="本地库未命中时，先给出 B 站检索入口，方便快速找到适合课堂的公开视频。",
                heat=0.92,
            ),
            ResourceDTO(
                resource_id=f"fallback_zhihu_{hashlib.md5(('zhihu:' + keyword).encode('utf-8')).hexdigest()[:10]}",
                title=f"{keyword} - 知乎检索入口",
                type=resource_type,
                summary="适合查找概念讲解、教学经验与题目解析的问答检索入口。",
                tags=[keyword, stage_label, subject_label, "zhihu"],
                grade=stage_label,
                subject=subject_label,
                duration=max(10, min(request.duration or 30, 45)),
                price=0.0,
                source="zhihu",
                url=f"https://www.zhihu.com/search?type=content&q={encoded_keyword}",
                score=0.82,
                reason="本地库未命中时，知乎适合补充概念说明、类比解释和教师备课参考。",
                heat=0.78,
            ),
            ResourceDTO(
                resource_id=f"fallback_smartedu_{hashlib.md5(('smartedu:' + keyword).encode('utf-8')).hexdigest()[:10]}",
                title=f"{keyword} - 国家中小学智慧教育平台",
                type=resource_type,
                summary="国家级课程与课堂资源入口，适合作为权威备课补充。",
                tags=[keyword, stage_label, subject_label, "smartedu"],
                grade=stage_label,
                subject=subject_label,
                duration=max(15, min(request.duration or 30, 60)),
                price=0.0,
                source="smartedu",
                url="https://basic.smartedu.cn/",
                score=0.86,
                reason="本地库未命中时，国家中小学智慧教育平台可作为权威补充资源。",
                heat=0.85,
            ),
        ]

    def _format_response(
        self,
        request: RequestDTO,
        intent: list[str],
        resources: list[ResourceDTO | dict[str, object]],
        total_candidates: int,
        fallback_used: bool,
    ) -> dict:
        normalized = [self._normalize_output_item(item, request) for item in resources[: self.top_k]]
        message = ""
        if fallback_used and total_candidates == 0:
            message = f"未召回到匹配资源，已返回常见平台的检索入口：{request.keyword or request.knowledge_point or request.target_goal}"
        return {
            "intent": intent,
            "total_candidates": total_candidates,
            "returned": len(normalized),
            "fallback_used": fallback_used,
            "recommended_resources": normalized,
            "resources": normalized,
            **({"message": message} if message else {}),
        }

    def _normalize_output_item(self, item: ResourceDTO | dict[str, object], request: RequestDTO) -> dict[str, object]:
        if isinstance(item, ResourceDTO):
            return self._normalize_recommended_item(item, request)
        return self._normalize_recommended_item(item, request)


router = APIRouter(prefix="/api/v1/teacher", tags=["recommendation"])
feedback_repo = FeedbackRepository()
RecommendationEngine = ResourceRecommendAgent
default_engine = ResourceRecommendAgent()


@router.post("/recommend")
async def recommend_resources(request: RequestDTO) -> dict:
    result = get_recommendations(request.model_dump())
    items = result.get("recommended_resources")
    if not isinstance(items, list):
        items = []
    result["recommended_resources"] = items
    result["resources"] = items
    result["returned"] = len(items)
    result["fallback_used"] = len(items) == 0
    return result


@router.post("/track-feedback", response_model=FeedbackAckDTO)
async def track_feedback(payload: TeacherFeedbackDTO) -> FeedbackAckDTO:
    try:
        feedback_repo.insert_feedback(payload)
        return FeedbackAckDTO()
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"track feedback failed: {error}")


def create_recommendation_app() -> FastAPI:
    app = FastAPI(title="Recommendation Service", version="1.0.0")
    app.include_router(router)
    return app
