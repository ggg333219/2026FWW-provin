"""Recommendation service package for AI teaching platform."""

from .adapters import BaseSourceAdapter, LocalDBAdapter, WebVideoAdapter
from .schemas import RequestDTO, ResourceDTO, TeacherFeedbackDTO
from .service import RecommendationEngine, create_recommendation_app

__all__ = [
	"BaseSourceAdapter",
	"LocalDBAdapter",
	"WebVideoAdapter",
	"RequestDTO",
	"ResourceDTO",
	"TeacherFeedbackDTO",
	"RecommendationEngine",
	"create_recommendation_app",
]
