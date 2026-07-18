import os
import re
import time
from dataclasses import dataclass
from typing import Any

try:
    from .schema import build_reconstruction_schema
except ImportError:
    from schema import build_reconstruction_schema


@dataclass
class ReconstructionConfig:
    mode: str = "hybrid"
    max_points: int = 5


class LessonReconstructor:
    """把页级解析内容重构为章节与讲授节点。"""

    def __init__(self, config: ReconstructionConfig | None = None):
        self.config = config or ReconstructionConfig(
            mode=os.getenv("AI_RECONSTRUCT_MODE", "hybrid"),
            max_points=int(os.getenv("AI_RECONSTRUCT_MAX_POINTS", "5")),
        )

    def reconstruct(self, parsed_document: dict[str, Any]) -> dict[str, Any]:
        started_at = time.time()
        pages = parsed_document.get("parsed_pages", [])
        teaching_nodes = self._build_nodes(pages)
        chapters = self._build_chapters(teaching_nodes)
        return build_reconstruction_schema(parsed_document, chapters, teaching_nodes, started_at)

    def _build_nodes(self, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []

        for index, page_item in enumerate(pages, start=1):
            page_num = page_item.get("page", index)
            content = (page_item.get("content") or "").strip()
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            title = self._infer_title(lines, page_num)
            summary = self._build_summary(lines, title)
            core_points = self._extract_core_points(lines)
            examples = self._extract_examples(lines)
            confusions = self._extract_confusions(title, core_points)

            nodes.append(
                {
                    "node_id": f"node_{page_num:03d}",
                    "title": title,
                    "source_pages": [page_num],
                    "summary": summary,
                    "core_points": core_points,
                    "examples": examples,
                    "common_confusions": confusions,
                    "recommended_explanation_order": [
                        "开场点题",
                        "解释核心概念",
                        "结合例子说明",
                        "总结与过渡",
                    ],
                    "estimated_duration": self._estimate_duration(summary, core_points),
                    "next_node_id": None,
                }
            )

        for idx in range(len(nodes) - 1):
            nodes[idx]["next_node_id"] = nodes[idx + 1]["node_id"]

        return nodes

    def _build_chapters(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chapters: list[dict[str, Any]] = []

        current_title = "课程导学"
        current_nodes: list[str] = []
        chapter_index = 1

        for node in nodes:
            node_title = node.get("title", "")
            inferred_chapter = self._infer_chapter_title(node_title)
            if inferred_chapter and current_nodes:
                chapters.append(
                    {
                        "chapter_id": f"chapter_{chapter_index:03d}",
                        "title": current_title,
                        "node_ids": current_nodes,
                    }
                )
                chapter_index += 1
                current_title = inferred_chapter
                current_nodes = []
            elif inferred_chapter:
                current_title = inferred_chapter

            current_nodes.append(node["node_id"])

        if current_nodes:
            chapters.append(
                {
                    "chapter_id": f"chapter_{chapter_index:03d}",
                    "title": current_title,
                    "node_ids": current_nodes,
                }
            )

        return chapters

    @staticmethod
    def _infer_title(lines: list[str], page_num: int) -> str:
        if not lines:
            return f"第{page_num}页主题"
        first = lines[0]
        if len(first) <= 40:
            return first
        return f"第{page_num}页核心内容"

    def _build_summary(self, lines: list[str], title: str) -> str:
        if not lines:
            return f"本节点围绕“{title}”展开，需要教师补充具体内容。"
        body = "；".join(lines[1:3]) if len(lines) > 1 else lines[0]
        return f"本节点重点讲解“{title}”，核心信息包括：{body[:180]}。"

    def _extract_core_points(self, lines: list[str]) -> list[str]:
        points: list[str] = []
        for line in lines[1 : self.config.max_points + 2]:
            candidate = re.sub(r"^[\-•*\d.、\s]+", "", line).strip()
            if candidate and candidate not in points:
                points.append(candidate[:80])
        if not points and lines:
            points.append(lines[0][:80])
        return points[: self.config.max_points]

    @staticmethod
    def _extract_examples(lines: list[str]) -> list[str]:
        keywords = ("例如", "比如", "案例", "应用", "场景")
        examples: list[str] = []
        for line in lines:
            if any(keyword in line for keyword in keywords):
                examples.append(line[:100])
        return examples[:3]

    @staticmethod
    def _extract_confusions(title: str, core_points: list[str]) -> list[str]:
        confusions = [f"{title}的核心概念是什么", f"{title}和前面知识点有什么关系"]
        if core_points:
            confusions.append(f"为什么要理解“{core_points[0]}”")
        return confusions[:3]

    @staticmethod
    def _estimate_duration(summary: str, core_points: list[str]) -> int:
        baseline = 45 + len(core_points) * 20
        if len(summary) > 100:
            baseline += 15
        return baseline

    @staticmethod
    def _infer_chapter_title(node_title: str) -> str | None:
        match = re.match(r"^(第[一二三四五六七八九十0-9]+[章节单元部分].*)", node_title)
        if match:
            return match.group(1)
        return None