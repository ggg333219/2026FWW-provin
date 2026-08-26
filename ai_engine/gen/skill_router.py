"""
Skill Router — S3/S4 课件生成的多 Skill 调度层

职责：
  接收 intent + evidence + skill_id，
  调用对应的 skill（deck-skill / pptx-skill），
  返回统一格式的节点树 + 设计元数据。

接口：
  GET  /api/v1/skill/list       — 列举可用 skills
  POST /api/v1/skill/deck      — 生成 HTML 幻灯片（deck-skill）
  POST /api/v1/skill/pptx      — 生成结构化节点树（pptx-skill，增强设计元数据）

设计原则：
  - 遵循项目 Skill 开发规范（docs/design/skills/开发skill注意事项.md）
  - LLM 调用统一走 core.llm.LLMClient，不自己 new OpenAI()
  - 数据模型统一引用 core.schema，不自建重复结构
  - 新增 Skill 只需在此注册，无需修改 main.py 以外的现有文件
"""

import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# 统一 LLM 客户端
from ai_engine.core.llm import LLMClient
from .skills.deck_swiss_edu.generator import DeckGenerator

router = APIRouter(prefix="/api/v1/skill", tags=["S3-Skill"])


# ---------------------------------------------------------------------------
# 请求 / 响应模型
# ---------------------------------------------------------------------------

class SkillListResponse(BaseModel):
    """GET /api/v1/skill/list 的响应。"""
    skills: list[dict[str, Any]]


class DeckRequest(BaseModel):
    """POST /api/v1/skill/deck 的请求。"""
    intent: dict[str, Any] = Field(description="结构化教学意图（至少含 title / key_points）")
    evidence_packet: Optional[dict[str, Any]] = Field(default=None, description="知识库证据包")
    nodes: Optional[list[dict[str, Any]]] = Field(default=None, description="已有节点树，直接渲染为幻灯片，跳过 LLM 生成")
    template_id: str = Field(default="deck-swiss-edu", description="模板 ID（当前仅支持 deck-swiss-edu）")
    palette: str = Field(default="klein-blue", description="配色方案：klein-blue / lemon-yellow / neon-green / safety-orange")


class DeckResponse(BaseModel):
    """POST /api/v1/skill/deck 的响应。"""
    skill_id: str
    slides: list[dict[str, Any]]
    palette: str
    html_path: str
    html_url: str
    page_count: int


class PptxSkillRequest(BaseModel):
    """POST /api/v1/skill/pptx 的请求（设计规范增强版）。"""
    intent: dict[str, Any]
    evidence_packet: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Skill 注册表（新增 skill 在此追加）
# ---------------------------------------------------------------------------

SKILL_REGISTRY: dict[str, dict[str, Any]] = {
    "deck-swiss-edu": {
        "id": "deck-swiss-edu",
        "name": "Swiss 教育风格",
        "name_en": "Swiss International (Education)",
        "mode": "deck",
        "description": "教学课件专用 HTML 幻灯片，22 种 Swiss 国际主义布局，Klein Blue 主调。",
        "surface": "web",
        "scenario": "education",
    },
    "pptx-enhanced": {
        "id": "pptx-enhanced",
        "name": "增强设计版 PPTX",
        "mode": "pptx",
        "description": "在原有 PPTX 生成基础上，注入 deck-skill 的设计规范（布局映射 + 配色系统），提升视觉质量。",
        "surface": "file",
        "scenario": "education",
    },
}


# ---------------------------------------------------------------------------
# 路由实现
# ---------------------------------------------------------------------------

@router.get("/list", response_model=SkillListResponse)
async def list_skills():
    """
    GET /api/v1/skill/list — 列举所有可用 skills。

    返回当前注册的所有 skill 元信息。
    """
    skills = [
        {
            "id": info["id"],
            "name": info["name"],
            "mode": info["mode"],
            "description": info["description"],
            "surface": info.get("surface", "web"),
        }
        for info in SKILL_REGISTRY.values()
    ]
    return SkillListResponse(skills=skills)


@router.post("/deck", response_model=DeckResponse)
async def generate_deck(req: DeckRequest):
    """
    POST /api/v1/skill/deck — 使用 deck-skill 生成 HTML 幻灯片。

    流程：
      1. 接收 intent + evidence_packet
      2. 调用 DeckGenerator.generate()
      3. 返回 slides JSON + HTML 文件路径

    可选配色：klein-blue / lemon-yellow / neon-green / safety-orange
    """
    if req.template_id != "deck-swiss-edu":
        raise HTTPException(
            status_code=400,
            detail=f"未知 template_id：{req.template_id}，当前仅支持 deck-swiss-edu",
        )

    try:
        generator = DeckGenerator()
        result = generator.generate(
            intent=req.intent,
            evidence_packet=req.evidence_packet,
            nodes=req.nodes,
            palette=req.palette,
        )
        return DeckResponse(
            skill_id="deck-swiss-edu",
            slides=result["slides"],
            palette=result["palette"],
            html_path=result["html_path"],
            html_url=result.get("html_url", ""),
            page_count=result["page_count"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deck 生成失败: {str(e)}")


@router.post("/pptx")
async def generate_pptx_enhanced(req: PptxSkillRequest):
    """
    POST /api/v1/skill/pptx — 增强设计版 PPTX 节点树。

    将 deck-skill 的设计规范（布局映射、配色系统）注入 OutlineBuilder 的 LLM prompt，
    返回带 design_hints 的结构化节点树，供后续 PPTExporter 渲染。

    当前为存根实现，后续 Phase 2/3 完善。
    """
    # TODO Phase 2: 实现设计规范注入逻辑
    raise HTTPException(
        status_code=501,
        detail="pptx-enhanced 模式尚在开发中，请使用 deck-skill 生成 HTML 预览",
    )
