from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from .schemas import RequestDTO, ResourceDTO, ResourceType


class BaseSourceAdapter(ABC):
    """统一多资源源搜索接口；新增数据源仅需实现 search。"""

    source_name: str = "unknown"

    @abstractmethod
    def search(self, request: RequestDTO, expanded_keywords: list[str]) -> list[ResourceDTO]:
        raise NotImplementedError


class LocalDBAdapter(BaseSourceAdapter):
    source_name = "local_db"

    def __init__(self, rows: Iterable[dict] | None = None):
        self.rows = list(rows or _default_local_rows())

    def search(self, request: RequestDTO, expanded_keywords: list[str]) -> list[ResourceDTO]:
        keyword_set = {kw.lower() for kw in expanded_keywords if kw.strip()}
        results: list[ResourceDTO] = []
        for row in self.rows:
            if row.get("type") != request.type.value:
                continue
            searchable = " ".join(
                [row.get("title", ""), row.get("summary", ""), " ".join(row.get("tags", []))]
            ).lower()
            if keyword_set and not any(word in searchable for word in keyword_set):
                continue
            results.append(
                ResourceDTO(
                    resource_id=row["resource_id"],
                    title=row["title"],
                    type=ResourceType(row["type"]),
                    summary=row["summary"],
                    tags=row.get("tags", []),
                    grade=row.get("grade", ""),
                    subject=row.get("subject", ""),
                    duration=int(row.get("duration", 0)),
                    price=float(row.get("price", 0.0)),
                    source=self.source_name,
                    url=row["url"],
                    heat=float(row.get("heat", 0.0)),
                )
            )
        return results


class WebVideoAdapter(BaseSourceAdapter):
    source_name = "web_video"

    def __init__(self, rows: Iterable[dict] | None = None):
        self.rows = list(rows or _default_web_rows())

    def search(self, request: RequestDTO, expanded_keywords: list[str]) -> list[ResourceDTO]:
        if request.type != ResourceType.WEB_COURSE:
            return []

        keyword_set = {kw.lower() for kw in expanded_keywords if kw.strip()}
        results: list[ResourceDTO] = []
        for row in self.rows:
            searchable = " ".join(
                [row.get("title", ""), row.get("summary", ""), " ".join(row.get("tags", []))]
            ).lower()
            if keyword_set and not any(word in searchable for word in keyword_set):
                continue
            results.append(
                ResourceDTO(
                    resource_id=row["resource_id"],
                    title=row["title"],
                    type=ResourceType(row["type"]),
                    summary=row["summary"],
                    tags=row.get("tags", []),
                    grade=row.get("grade", ""),
                    subject=row.get("subject", ""),
                    duration=int(row.get("duration", 0)),
                    price=float(row.get("price", 0.0)),
                    source=self.source_name,
                    url=row["url"],
                    heat=float(row.get("heat", 0.0)),
                )
            )
        return results


def _default_local_rows() -> list[dict]:
    return [
        {
            "resource_id": "qb_alg_001",
            "title": "函数与方程分层题单",
            "type": "题库",
            "summary": "覆盖函数单调性、零点与二分思想，含梯度练习。",
            "tags": ["函数", "方程", "二分"],
            "grade": "高一",
            "subject": "数学",
            "duration": 35,
            "price": 0,
            "url": "https://resource.example.edu/qb_alg_001",
            "heat": 0.82,
        },
        {
            "resource_id": "qb_phy_002",
            "title": "牛顿第二定律专题题库",
            "type": "题库",
            "summary": "从受力分析到公式建模，附课堂投影版。",
            "tags": ["力学", "受力分析", "建模"],
            "grade": "高一",
            "subject": "物理",
            "duration": 40,
            "price": 12,
            "url": "https://resource.example.edu/qb_phy_002",
            "heat": 0.75,
        },
    ]


def _default_web_rows() -> list[dict]:
    return [
        {
            "resource_id": "mooc_math_101",
            "title": "函数图像与性质速通课",
            "type": "网课",
            "summary": "通过图像直观讲解定义域、值域与单调性。",
            "tags": ["函数", "图像", "单调性"],
            "grade": "高一",
            "subject": "数学",
            "duration": 28,
            "price": 0,
            "url": "https://video.example.edu/mooc_math_101",
            "heat": 0.91,
        },
        {
            "resource_id": "mooc_phy_210",
            "title": "受力分析与动力学基础",
            "type": "网课",
            "summary": "用动画演示牛顿第二定律在实际问题中的应用。",
            "tags": ["力学", "牛顿定律", "实验"],
            "grade": "高一",
            "subject": "物理",
            "duration": 32,
            "price": 9.9,
            "url": "https://video.example.edu/mooc_phy_210",
            "heat": 0.88,
        },
    ]
