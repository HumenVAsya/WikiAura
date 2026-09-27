"""Schemas package."""

from app.schemas.analytics import (
    AIInterpretationDTO,
    AnalyticsResultDTO,
    ComparisonMetricsDTO,
    ConfidenceLevel,
    LanguageAnalyticsDTO,
    TimeSeriesPoint,
    TrendDirection,
    TrendMetricsDTO,
)
from app.schemas.requests import (
    AnalyzeRequest,
    AnalyzeTopicRequest,
    AnalyzeTopicResponse,
    LanguagePageviewsResult,
    NaturalLanguageAnalyticsRequest,
    PageviewItem,
    TrendAnalyticsRequest,
    WikipediaQueryParams,
    WikiTrendAnalysisRequest,
    WikiTrendAnalysisResponse,
)

__all__ = [
    "AIInterpretationDTO",
    "AnalyticsResultDTO",
    "AnalyzeRequest",
    "AnalyzeTopicRequest",
    "AnalyzeTopicResponse",
    "ComparisonMetricsDTO",
    "ConfidenceLevel",
    "LanguageAnalyticsDTO",
    "LanguagePageviewsResult",
    "NaturalLanguageAnalyticsRequest",
    "PageviewItem",
    "TimeSeriesPoint",
    "TrendAnalyticsRequest",
    "TrendDirection",
    "TrendMetricsDTO",
    "WikipediaQueryParams",
    "WikiTrendAnalysisRequest",
    "WikiTrendAnalysisResponse",
]
