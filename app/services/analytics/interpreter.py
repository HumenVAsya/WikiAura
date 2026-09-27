"""AI Synthesis layer using Google Gemini and instructor to convert quantitative metrics into qualitative insights."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional
import instructor

from app.schemas.analytics import (
    AIInterpretationDTO,
    ComparisonMetricsDTO,
    ConfidenceLevel,
    TrendDirection,
    TrendMetricsDTO,
)
from app.services.llm_parser import (
    DEFAULT_GEMINI_MODEL,
    FALLBACK_GEMINI_MODELS,
    get_instructor_gemini_client,
)

logger = logging.getLogger(__name__)


def build_analytics_synthesis_prompt(
    topic: str,
    start_date: str,
    end_date: str,
    granularity: str,
    language_metrics: Dict[str, TrendMetricsDTO],
    comparison: Optional[ComparisonMetricsDTO] = None,
    source_topic: Optional[str] = None,
) -> str:
    """Format structured analytical prompt for LLM executive synthesis."""
    lines = [
        f"Topic: {topic}" + (f" (Native hub: {source_topic})" if source_topic else ""),
        f"Timeframe: {start_date} to {end_date} (Granularity: {granularity})",
        "",
        "Aggregated Metrics by Language Edition:",
    ]

    for lang, m in language_metrics.items():
        mom_str = f"{m.mom_growth_percent:+.1f}%" if m.mom_growth_percent is not None else "N/A"
        yoy_str = f"{m.yoy_growth_percent:+.1f}%" if m.yoy_growth_percent is not None else "N/A"
        lines.append(
            f"  - Wikipedia [{lang}]: Total Views={m.total_views:,}, Avg/Period={m.average_views:,.0f}, "
            f"MoM Growth={mom_str}, YoY Growth={yoy_str}, Volatility={m.volatility_score:.2f}, "
            f"Direction='{m.trend_direction}', Anomalies={m.anomaly_count}, Peak={m.peak_views:,} on {m.peak_date}"
        )

    if comparison:
        lines.extend([
            "",
            "Cross-Language Comparison:",
            f"  - Dominant Edition: Wikipedia [{comparison.dominant_language}]",
            f"  - Fastest Growing Edition: Wikipedia [{comparison.fastest_growing_language or 'N/A'}]",
            f"  - Attention Share: {comparison.language_shares_percent}",
        ])

    lines.extend([
        "",
        "Task:",
        "Analyze these calculated metrics and synthesize an executive business summary (`AIInterpretationDTO`).",
        "Explain whether interest is genuinely growing, declining, seasonal, or driven by a singular viral spike.",
        "Provide actionable business takeaways regarding language/market traction.",
    ])

    return "\n".join(lines)


def generate_heuristic_interpretation(
    topic: str,
    language_metrics: Dict[str, TrendMetricsDTO],
    comparison: Optional[ComparisonMetricsDTO] = None,
) -> AIInterpretationDTO:
    """Deterministic fallback synthesis if LLM API is unavailable or keys are missing."""
    if not language_metrics:
        return AIInterpretationDTO(
            trend_summary=f"No pageview activity recorded for topic '{topic}'.",
            direction="stable",
            confidence="low",
            seasonality_detected=False,
            key_drivers=["Insufficient time series data to compute direction."],
            business_takeaway="Broaden the timeframe or verify article aliases across language editions.",
        )

    dom_lang = comparison.dominant_language if comparison else next(iter(language_metrics))
    m = language_metrics.get(dom_lang) or next(iter(language_metrics.values()))

    if m.confidence_score >= 0.75:
        confidence: ConfidenceLevel = "high"
    elif m.confidence_score >= 0.45:
        confidence = "medium"
    else:
        confidence = "low"

    drivers: List[str] = []
    if m.anomaly_count > 0:
        drivers.append(f"Detected {m.anomaly_count} anomalous viral spike(s), peaking on {m.peak_date} with {m.peak_views:,} views.")
    if m.yoy_growth_percent is not None:
        drivers.append(f"Annual YoY trajectory: {m.yoy_growth_percent:+.1f}%.")
    if comparison and comparison.fastest_growing_language:
        drivers.append(f"Fastest growing language edition: [{comparison.fastest_growing_language}].")

    if m.trend_direction == "growing":
        summary = f"Steady positive interest expansion observed for '{topic}' led by Wikipedia [{dom_lang}]."
        takeaway = "Sustained audience interest suggests strong organic demand and viable expansion potential."
    elif m.trend_direction == "declining":
        summary = f"Cooling audience attention detected for '{topic}' across observed language editions."
        takeaway = "Attention has normalized past its peak; focus on retention or pivot to high-performing sub-segments."
    elif m.trend_direction == "volatile":
        summary = f"Interest in '{topic}' shows high volatility with episodic spikes rather than steady adoption."
        takeaway = "Topic attention is event-driven; align marketing and content releases with external news cycles."
    else:
        summary = f"Stable, recurring baseline reading patterns for '{topic}'."
        takeaway = "Consistent baseline traffic provides a predictable foundation for targeted engagement."

    return AIInterpretationDTO(
        trend_summary=summary,
        direction=m.trend_direction,
        confidence=confidence,
        seasonality_detected=(m.volatility_score < 0.35 and m.total_views > 1000),
        key_drivers=drivers,
        business_takeaway=takeaway,
    )


async def synthesize_trend_insights(
    topic: str,
    start_date: str,
    end_date: str,
    granularity: str,
    language_metrics: Dict[str, TrendMetricsDTO],
    comparison: Optional[ComparisonMetricsDTO] = None,
    source_topic: Optional[str] = None,
    client: Optional[instructor.AsyncInstructor] = None,
) -> AIInterpretationDTO:
    """Synthesize quantitative metrics into qualitative AIInterpretationDTO using Gemini or fallback."""
    prompt = build_analytics_synthesis_prompt(
        topic=topic,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        language_metrics=language_metrics,
        comparison=comparison,
        source_topic=source_topic,
    )

    if client is not None:
        try:
            return await client.chat.completions.create(
                model=DEFAULT_GEMINI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert market intelligence and data analytics consultant. "
                            "Analyze quantitative time-series metrics from Wikipedia and return structured insights."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_model=AIInterpretationDTO,
            )
        except Exception as exc:
            logger.warning("Provided instructor client synthesis failed: %s. Using heuristic fallback.", exc)
            return generate_heuristic_interpretation(topic, language_metrics, comparison)

    try:
        gemini_client = get_instructor_gemini_client()
    except Exception as exc:
        logger.info("No Gemini API key available (%s). Utilizing deterministic heuristic synthesis.", exc)
        return generate_heuristic_interpretation(topic, language_metrics, comparison)

    candidate_models = [DEFAULT_GEMINI_MODEL] + [
        m for m in FALLBACK_GEMINI_MODELS if m != DEFAULT_GEMINI_MODEL
    ]

    for model_name in candidate_models:
        try:
            logger.info("Synthesizing trend insights with model '%s'...", model_name)
            result = await gemini_client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert market intelligence and data analytics consultant. "
                            "Analyze quantitative time-series metrics from Wikipedia and return structured insights."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_model=AIInterpretationDTO,
            )
            return result
        except Exception as exc:
            logger.warning("Model '%s' synthesis attempt failed: %s", model_name, exc)

    logger.warning("All LLM synthesis attempts failed. Falling back to heuristic synthesis.")
    return generate_heuristic_interpretation(topic, language_metrics, comparison)
