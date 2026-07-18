from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ResourceType(str, Enum):
    WEB_COURSE = "网课"
    QUESTION_BANK = "题库"


class StageType(str, Enum):
    PRIMARY = "小学"
    MIDDLE = "初中"
    HIGH = "高中"
    UNIVERSITY = "大学"
    ADULT = "成人"


class FeedbackAction(str, Enum):
    CLICK = "click"
    FAVORITE = "favorite"
    IGNORE = "ignore"
    REFRESH = "refresh"


class RequestDTO(BaseModel):
    keyword: str = Field(default="", description="教师输入关键词")
    target_goal: str = Field(default="", description="教学目标")
    knowledge_point: str = Field(default="", description="知识点")
    subject: str = Field(default="", description="学科")
    stage: StageType = Field(default=StageType.HIGH)
    type: ResourceType = Field(default=ResourceType.WEB_COURSE)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0, description="期望难度，0-1")
    duration: int = Field(default=30, ge=1, description="期望时长（分钟）")
    budget: float = Field(default=0.0, ge=0.0, description="预算（元）")
    source_preference: list[str] = Field(default_factory=list, description="偏好资源源")


class ResourceDTO(BaseModel):
    resource_id: str
    title: str
    type: ResourceType
    summary: str
    tags: list[str] = Field(default_factory=list)
    grade: str = ""
    subject: str = ""
    duration: int = Field(default=0, ge=0)
    price: float = Field(default=0.0, ge=0.0)
    source: str
    url: HttpUrl
    score: float = Field(default=0.0)
    reason: str = ""
    heat: float = Field(default=0.0, ge=0.0)


class TeacherFeedbackDTO(BaseModel):
    teacher_id: str
    resource_id: str
    action: FeedbackAction
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackAckDTO(BaseModel):
    ok: Literal[True] = True
    message: str = "feedback tracked"
