"""WikiAura Analytics Engine: 4-stage pipeline for Wikipedia time-series metrics and AI insights."""

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
from app.services.analytics.cleaner import (
    parse_boundary_date,
    standardize_pageviews_to_dataframe,
)
from app.services.analytics.facade import WikipediaTrendsAnalyzer
from app.services.analytics.interpreter import (
    build_analytics_synthesis_prompt,
    generate_heuristic_interpretation,
    synthesize_trend_insights,
)
from app.services.analytics.strategies import (
    BaseAnalyticsStrategy,
    ComparisonAnalysisStrategy,
    TrendAnalysisStrategy,
)

__all__ = [
    "AIInterpretationDTO",
    "AnalyticsResultDTO",
    "BaseAnalyticsStrategy",
    "ComparisonAnalysisStrategy",
    "ComparisonMetricsDTO",
    "ConfidenceLevel",
    "LanguageAnalyticsDTO",
    "TimeSeriesPoint",
    "TrendAnalysisStrategy",
    "TrendDirection",
    "TrendMetricsDTO",
    "WikipediaTrendsAnalyzer",
    "build_analytics_synthesis_prompt",
    "generate_heuristic_interpretation",
    "parse_boundary_date",
    "standardize_pageviews_to_dataframe",
    "synthesize_trend_insights",
]
