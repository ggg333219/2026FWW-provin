from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote_plus

from openai import OpenAI

try:
    from .qa import resolve_llm_base_url
except ImportError:
    from qa import resolve_llm_base_url


def _extract_json_payload(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(cleaned[start : end + 1])
    except Exception:
        return {}


def _build_search_url(keyword: str, source: str = "") -> str:
    safe_keyword = quote_plus((keyword or "选择排序").strip() or "选择排序")
    source_text = (source or "").strip().lower()
    if "51教习" in source or "51jiaoxi" in source_text or "学科网" in source or "zxxk" in source_text or "xkw" in source_text:
        return f"https://www.51jiaoxi.com/search?keyword={safe_keyword}"
    if "知乎" in source or "zhihu" in source_text:
        return f"https://www.zhihu.com/search?type=content&q={safe_keyword}"
    if "b站" in source or "bilibili" in source_text:
        return f"https://search.bilibili.com/all?keyword={safe_keyword}"
    return f"https://search.bilibili.com/all?keyword={safe_keyword}"


def _default_association_queries(keyword: str) -> list[str]:
    raw_keyword = (keyword or "选择排序").strip() or "选择排序"
    return [
        f"{raw_keyword} 入门讲解",
        f"{raw_keyword} 典型例题",
        f"{raw_keyword} 易错点",
    ]


def _generate_association_queries(keyword: str, api_key: str, model: str, base_url: str) -> list[str]:
    if not api_key:
        return _default_association_queries(keyword)

    raw_keyword = (keyword or "选择排序").strip() or "选择排序"
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            temperature=0.4,
            timeout=8,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是教学搜索词优化助手。"
                        "请仅输出 JSON，格式为{\"queries\":[\"...\",\"...\",\"...\"]}。"
                        "queries 必须给出 3 条围绕输入关键词的联想搜索词，"
                        "不要包含“关键词联想”这四个字。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"核心关键词：{raw_keyword}",
                },
            ],
        )
        payload = _extract_json_payload(response.choices[0].message.content or "")
        raw_queries = payload.get("queries")
        if not isinstance(raw_queries, list):
            return _default_association_queries(raw_keyword)

        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_queries:
            text = str(item or "").strip()
            if not text:
                continue
            text = text.replace("关键词联想", "").strip()
            if not text:
                continue
            lower = text.lower()
            if lower in seen:
                continue
            seen.add(lower)
            normalized.append(text)

        defaults = _default_association_queries(raw_keyword)
        for text in defaults:
            if len(normalized) >= 3:
                break
            if text.lower() in seen:
                continue
            seen.add(text.lower())
            normalized.append(text)

        return normalized[:3]
    except Exception:
        return _default_association_queries(raw_keyword)


def _ensure_https_url(url: str, keyword: str = "", source: str = "") -> str:
    cleaned_url = str(url or "").strip()
    if cleaned_url.startswith("https://"):
        return cleaned_url
    if cleaned_url.startswith("http://"):
        return "https://" + cleaned_url[len("http://") :]

    return _build_search_url(keyword, source)


def _selection_sort_fallback(keyword: str, association_queries: list[str] | None = None) -> list[dict[str, Any]]:
    raw_keyword = (keyword or "选择排序").strip() or "选择排序"
    queries = [q for q in (association_queries or []) if str(q or "").strip()]
    if len(queries) < 3:
        for q in _default_association_queries(raw_keyword):
            if len(queries) >= 3:
                break
            if q not in queries:
                queries.append(q)

    bilibili_query_1 = quote_plus(queries[0])
    xuexi_query = quote_plus(queries[1])
    bilibili_query_2 = quote_plus(queries[2])
    return [
        {
            "title": f"B站：{queries[0]}",
            "url": f"https://search.bilibili.com/all?keyword={bilibili_query_1}",
            "source": "bilibili",
            "fit_reason": f"根据“{raw_keyword}”联想到“{queries[0]}”，适合课堂导入与核心概念讲解。",
            "type": "网课",
        },
        {
            "title": f"51教习：{queries[1]}",
            "url": f"https://www.51jiaoxi.com/search?keyword={xuexi_query}",
            "source": "51jiaoxi",
            "fit_reason": f"根据“{raw_keyword}”联想到“{queries[1]}”，便于获取配套课件、题单与课堂练习。",
            "type": "网课",
        },
        {
            "title": f"B站：{queries[2]}",
            "url": f"https://search.bilibili.com/all?keyword={bilibili_query_2}",
            "source": "bilibili",
            "fit_reason": f"根据“{raw_keyword}”联想到“{queries[2]}”，适合课堂巩固与课后复盘。",
            "type": "网课",
        },
    ]


def _normalize_items(raw_items: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or item.get("link") or "").strip()
        source = str(item.get("source") or "bilibili").strip() or "bilibili"
        fit_reason = str(item.get("fit_reason") or item.get("reason") or "").strip()
        item_type = str(item.get("type") or "网课").strip() or "网课"

        if not title:
            continue
        url = _ensure_https_url(url, title, source)
        if not fit_reason:
            fit_reason = "面向高中计算机教学，动态演示清晰，便于课堂讲解与练习。"

        normalized.append(
            {
                "title": title,
                "url": url,
                "source": source,
                "fit_reason": fit_reason,
                "type": item_type,
            }
        )

    return normalized


def get_recommendations(payload: dict[str, Any]) -> dict[str, Any]:
    """100% 大模型生成推荐，不查本地数据库；失败时强制返回 3 条兜底资源。"""
    keyword = str((payload or {}).get("keyword") or "").strip() or "选择排序"
    api_key = (os.getenv("AI_API_KEY") or "").strip()
    model = (os.getenv("AI_MODEL") or "qwen-turbo").strip()
    base_url, _ = resolve_llm_base_url(model)

    fallback_items: list[dict[str, Any]] | None = None

    def _get_fallback_items() -> list[dict[str, Any]]:
        nonlocal fallback_items
        if fallback_items is None:
            association_queries = _generate_association_queries(keyword, api_key, model, base_url)
            fallback_items = _selection_sort_fallback(keyword, association_queries)
        return fallback_items

    if not api_key:
        return {"recommended_resources": _selection_sort_fallback(keyword)}

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        system_prompt = (
            "你是智能教研资源推荐专家。"
            "必须只输出 JSON，根键名必须是 recommended_resources。"
            "recommended_resources 必须是数组，且至少 3 条。"
            "每条必须包含 title, url, source, fit_reason, type。"
            "如果没有精准资源，也要根据常识生成 B 站、51教习或知名平台可访问链接，绝不允许空数组。"
            "视频类讲解优先给 B 站搜索链接，课件、题单、试题类内容优先给 51教习搜索链接。"
            "标题和检索词必须围绕当前关键词做联想，不要套用固定模板词（如“复杂度分析”）。"
            f"本次核心搜索词是：{keyword}。请围绕该词生成推荐。"
        )
        user_prompt = (
            f"教师输入: {json.dumps(payload, ensure_ascii=False)}\n"
            f"核心关键词: {keyword}\n"
            "请直接返回 JSON。"
        )

        response = client.chat.completions.create(
            model=model,
            temperature=0.7,
            timeout=12,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_content = (response.choices[0].message.content or "").strip()
        print(f"AI Raw Response: {raw_content}", flush=True)
        print(f"DEBUG - AI Keyword: {keyword}", flush=True)

        parsed = _extract_json_payload(raw_content)
        raw_items = parsed.get("recommended_resources")
        if not isinstance(raw_items, list):
            raw_items = parsed.get("resources")
        items = _normalize_items(raw_items)
        if len(items) < 3:
            fallback = _get_fallback_items()
            items.extend(fallback[len(items) : 3])

        return {"recommended_resources": items[:3]}
    except Exception as error:
        print(f"AI Raw Response: request_failed:{error}", flush=True)
        print(f"DEBUG - AI Keyword: {keyword}", flush=True)
        return {"recommended_resources": _get_fallback_items()}
