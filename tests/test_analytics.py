"""Unit and integration tests for the 4-stage WikiAura Analytics Engine."""

from __future__ import annotations

from datetime import datetime
import pytest
from httpx import ASGITransport, AsyncClient
import numpy as np
import pandas as pd
import respx

from app.main import app
from app.schemas.analytics import (
    AIInterpretationDTO,
    AnalyticsResultDTO,
    ComparisonMetricsDTO,
    LanguageAnalyticsDTO,
    TrendMetricsDTO,
)
from app.schemas.requests import PageviewItem
from app.services.analytics.cleaner import standardize_pageviews_to_dataframe
from app.services.analytics.facade import WikipediaTrendsAnalyzer
from app.services.analytics.interpreter import (
    build_analytics_synthesis_prompt,
    generate_heuristic_interpretation,
    synthesize_trend_insights,
)
from app.services.analytics.strategies import (
    ComparisonAnalysisStrategy,
    TrendAnalysisStrategy,
)


# ============================================================================
# Stage 2: Validation & Standardization (Data Cleaning & Continuous Grid)
# ============================================================================


def test_standardize_pageviews_gap_filling_monthly():
    """Verify that gaps in monthly Wikipedia data are filled with 0 views to ensure continuity."""
    items = [
        PageviewItem(date="2023-01", timestamp="2023010100", views=1000),
        # 2023-02 is missing!
        PageviewItem(date="2023-03", timestamp="2023030100", views=1500),
        PageviewItem(date="2023-04", timestamp="2023040100", views=2000),
    ]

    df = standardize_pageviews_to_dataframe(
        items=items,
        start_date="20230101",
        end_date="20230401",
        granularity="monthly",
    )

    assert len(df) == 4
    assert df.loc[datetime(2023, 1, 1), "views"] == 1000
    assert df.loc[datetime(2023, 2, 1), "views"] == 0  # Missing month filled with 0
    assert df.loc[datetime(2023, 3, 1), "views"] == 1500
    assert df.loc[datetime(2023, 4, 1), "views"] == 2000
    assert df.loc[datetime(2023, 2, 1), "is_partial"] is False or df.loc[datetime(2023, 2, 1), "is_partial"] == False


def test_standardize_pageviews_empty_items():
    """Verify that an empty list of items creates a continuous zero-filled DataFrame."""
    df = standardize_pageviews_to_dataframe(
        items=[],
        start_date="20230101",
        end_date="20230601",
        granularity="monthly",
    )

    assert len(df) == 6
    assert (df["views"] == 0).all()
    assert "date" in df.columns
    assert "timestamp" in df.columns


def test_standardize_pageviews_daily():
    """Verify daily frequency gap filling."""
    items = [
        PageviewItem(date="2023-01-01", timestamp="2023010100", views=100),
        # 2023-01-02 missing
        PageviewItem(date="2023-01-03", timestamp="2023010300", views=300),
    ]

    df = standardize_pageviews_to_dataframe(
        items=items,
        start_date="20230101",
        end_date="20230103",
        granularity="daily",
    )

    assert len(df) == 3
    assert df.loc[datetime(2023, 1, 2), "views"] == 0


# ============================================================================
# Stage 3: Analytical Engine (TrendAnalysisStrategy)
# ============================================================================


def test_trend_strategy_rolling_averages_and_volatility():
    """Verify rolling average calculation and volatility score."""
    dates = pd.date_range("2023-01-01", periods=6, freq="MS")
    # Series: 1000, 2000, 3000, 4000, 5000, 6000
    views = [1000, 2000, 3000, 4000, 5000, 6000]
    df = pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m") for d in dates],
            "timestamp": [d.strftime("%Y%m0100") for d in dates],
            "views": views,
            "is_partial": [False] * 6,
        },
        index=dates,
    )

    strategy = TrendAnalysisStrategy()
    metrics, points = strategy.analyze(df, granularity="monthly")

    assert metrics.total_views == 21000
    assert metrics.average_views == 3500.0
    assert metrics.median_views == 3500.0
    assert metrics.peak_views == 6000
    assert metrics.peak_date == "2023-06"
    assert metrics.trough_views == 1000
    assert metrics.trend_direction == "growing"

    # Rolling average window = 3
    # Point 0: 1000
    # Point 1: (1000 + 2000) / 2 = 1500
    # Point 2: (1000 + 2000 + 3000) / 3 = 2000
    # Point 5: (4000 + 5000 + 6000) / 3 = 5000
    assert points[0].rolling_average == 1000.0
    assert points[1].rolling_average == 1500.0
    assert points[2].rolling_average == 2000.0
    assert points[5].rolling_average == 5000.0

    # MoM growth: (6000 - 5000) / 5000 = +20.0%
    assert metrics.mom_growth_percent == 20.0


def test_trend_strategy_anomaly_detection_zscore():
    """Verify statistical anomaly detection when a viral spike exceeds Z > 2.5."""
    dates = pd.date_range("2023-01-01", periods=20, freq="MS")
    # Baseline stable around 1,000 views, with one massive viral spike of 50,000 at month 10
    views = [1000] * 20
    views[10] = 50000

    df = pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m") for d in dates],
            "timestamp": [d.strftime("%Y%m0100") for d in dates],
            "views": views,
            "is_partial": [False] * 20,
        },
        index=dates,
    )

    strategy = TrendAnalysisStrategy()
    metrics, points = strategy.analyze(df, granularity="monthly")

    assert metrics.anomaly_count >= 1
    assert points[10].is_anomaly is True
    assert points[10].z_score > 2.5
    assert points[0].is_anomaly is False


def test_trend_strategy_partial_month_exclusion_for_growth():
    """Verify that an in-progress partial month doesn't distort MoM growth calculation."""
    dates = pd.date_range("2023-01-01", periods=4, freq="MS")
    # Month 1: 1000, Month 2: 1200, Month 3: 1500 (complete)
    # Month 4: 50 (only 1 day in, marked is_partial=True)
    df = pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m") for d in dates],
            "timestamp": [d.strftime("%Y%m0100") for d in dates],
            "views": [1000, 1200, 1500, 50],
            "is_partial": [False, False, False, True],
        },
        index=dates,
    )

    strategy = TrendAnalysisStrategy()
    metrics, _ = strategy.analyze(df, granularity="monthly")

    # Evaluates complete month 3 against complete month 2: (1500 - 1200) / 1200 = +25.0%
    assert metrics.mom_growth_percent == 25.0


def test_trend_strategy_yoy_calculation():
    """Verify Year-over-Year (YoY) calculation compares with 12 months prior."""
    dates = pd.date_range("2022-01-01", periods=14, freq="MS")
    # Constant 1000 in 2022, 2000 in 2023
    views = [1000] * 12 + [2000, 2000]
    df = pd.DataFrame(
        {
            "date": [d.strftime("%Y-%m") for d in dates],
            "timestamp": [d.strftime("%Y%m0100") for d in dates],
            "views": views,
            "is_partial": [False] * 14,
        },
        index=dates,
    )

    strategy = TrendAnalysisStrategy()
    metrics, _ = strategy.analyze(df, granularity="monthly")

    # Latest month is index 13 (2023-02, views 2000), 12 periods prior is index 1 (2022-02, views 1000)
    # (2000 - 1000) / 1000 = +100.0%
    assert metrics.yoy_growth_percent == 100.0


# ============================================================================
# Stage 3: ComparisonAnalysisStrategy (Cross-Language Market Dynamics)
# ============================================================================


def test_comparison_strategy():
    """Verify dominant language, growth leader, attention shares, and correlation matrix."""
    dates = pd.date_range("2023-01-01", periods=5, freq="MS")

    df_en = pd.DataFrame(
        {"views": [1000, 2000, 3000, 4000, 5000]},
        index=dates,
    )
    df_uk = pd.DataFrame(
        {"views": [100, 200, 300, 400, 500]},  # Perfectly correlated with en
        index=dates,
    )

    metrics_en = TrendMetricsDTO(
        total_views=15000,
        average_views=3000.0,
        median_views=3000.0,
        std_dev=1414.2,
        volatility_score=0.47,
        mom_growth_percent=25.0,
        trend_direction="growing",
        confidence_score=0.9,
    )
    metrics_uk = TrendMetricsDTO(
        total_views=1500,
        average_views=300.0,
        median_views=300.0,
        std_dev=141.4,
        volatility_score=0.47,
        mom_growth_percent=50.0,
        trend_direction="growing",
        confidence_score=0.9,
    )

    strategy = ComparisonAnalysisStrategy()
    comp = strategy.compare(
        language_dfs={"en": df_en, "uk": df_uk},
        language_metrics={"en": metrics_en, "uk": metrics_uk},
    )

    assert comp.dominant_language == "en"
    assert comp.fastest_growing_language == "uk"  # 50% vs 25%
    # Total = 16500; en = 15000/16500 = 90.91%, uk = 1500/16500 = 9.09%
    assert comp.language_shares_percent["en"] == 90.91
    assert comp.language_shares_percent["uk"] == 9.09
    # Correlation between en and uk is 1.0
    assert comp.correlation_matrix["en"]["uk"] == 1.0
    assert comp.correlation_matrix["uk"]["en"] == 1.0


# ============================================================================
# Stage 4: Synthesis & Output (AI Interpretation Heuristic & Prompt)
# ============================================================================


def test_heuristic_interpretation_generation():
    """Verify deterministic fallback synthesis without LLM credentials."""
    metrics_en = TrendMetricsDTO(
        total_views=50000,
        average_views=5000.0,
        median_views=4800.0,
        std_dev=600.0,
        volatility_score=0.12,
        mom_growth_percent=15.0,
        yoy_growth_percent=35.0,
        trend_direction="growing",
        confidence_score=0.88,
        peak_date="2023-12",
        peak_views=6500,
        anomaly_count=0,
    )

    comp = ComparisonMetricsDTO(
        dominant_language="en",
        fastest_growing_language="en",
        language_shares_percent={"en": 100.0},
    )

    synth = generate_heuristic_interpretation(
        topic="Coffee",
        language_metrics={"en": metrics_en},
        comparison=comp,
    )

    assert synth.direction == "growing"
    assert synth.confidence == "high"
    assert "Coffee" in synth.trend_summary
    assert synth.business_takeaway is not None
    assert len(synth.business_takeaway) > 10


def test_build_analytics_prompt_formatting():
    """Verify prompt formatting for LLM contains key quantitative facts."""
    metrics = {
        "en": TrendMetricsDTO(
            total_views=10000,
            average_views=1000.0,
            median_views=1000.0,
            std_dev=100.0,
            volatility_score=0.1,
            mom_growth_percent=10.0,
            trend_direction="growing",
            confidence_score=0.9,
            peak_date="2023-10",
            peak_views=1500,
        )
    }
    prompt = build_analytics_synthesis_prompt(
        topic="Artificial intelligence",
        start_date="20230101",
        end_date="20231231",
        granularity="monthly",
        language_metrics=metrics,
        source_topic="Штучний інтелект",
    )

    assert "Artificial intelligence" in prompt
    assert "Штучний інтелект" in prompt
    assert "Wikipedia [en]" in prompt
    assert "MoM Growth=+10.0%" in prompt


# ============================================================================
# Facade Pattern & End-to-End Orchestration
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_wikipedia_trends_analyzer_facade():
    """Verify WikipediaTrendsAnalyzer orchestrates all 4 stages properly."""
    # Mock English Wikipedia interlanguage links
    respx.get("https://en.wikipedia.org/w/api.php").respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "123": {
                        "title": "Quantum computing",
                        "langlinks": [{"lang": "uk", "*": "Квантовий комп'ютер"}],
                    }
                }
            }
        },
    )

    # Mock pageviews for English
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/Quantum_computing/monthly/2023010100/2023030100"
    ).respond(
        status_code=200,
        json={
            "items": [
                {"project": "en.wikipedia", "article": "Quantum_computing", "granularity": "monthly", "timestamp": "2023010100", "views": 10000},
                {"project": "en.wikipedia", "article": "Quantum_computing", "granularity": "monthly", "timestamp": "2023020100", "views": 12000},
                {"project": "en.wikipedia", "article": "Quantum_computing", "granularity": "monthly", "timestamp": "2023030100", "views": 15000},
            ]
        },
    )

    # Mock pageviews for Ukrainian
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/uk.wikipedia.org/all-access/user/%D0%9A%D0%B2%D0%B0%D0%BD%D1%82%D0%BE%D0%B2%D0%B8%D0%B9_%D0%BA%D0%BE%D0%BC%D0%BF%27%D1%8E%D1%82%D0%B5%D1%80/monthly/2023010100/2023030100"
    ).respond(
        status_code=200,
        json={
            "items": [
                {"project": "uk.wikipedia", "article": "Квантовий_комп'ютер", "granularity": "monthly", "timestamp": "2023010100", "views": 500},
                {"project": "uk.wikipedia", "article": "Квантовий_комп'ютер", "granularity": "monthly", "timestamp": "2023020100", "views": 600},
                {"project": "uk.wikipedia", "article": "Квантовий_комп'ютер", "granularity": "monthly", "timestamp": "2023030100", "views": 800},
            ]
        },
    )

    analyzer = WikipediaTrendsAnalyzer()
    async with AsyncClient() as client:
        result: AnalyticsResultDTO = await analyzer.analyze_topic(
            topic="Quantum computing",
            languages=["en", "uk"],
            start_date="20230101",
            end_date="20230301",
            granularity="monthly",
            client=client,
            include_ai_summary=True,
        )

    assert result.topic == "Quantum computing"
    assert "en" in result.languages
    assert "uk" in result.languages
    assert result.languages["en"].found is True
    assert result.languages["en"].metrics.total_views == 37000
    assert result.languages["uk"].found is True
    assert result.languages["uk"].metrics.total_views == 1900
    assert result.comparison.dominant_language == "en"
    assert result.ai_interpretation is not None
    assert result.ai_interpretation.direction == "growing"


# ============================================================================
# API Endpoint Integration Test
# ============================================================================


@pytest.mark.asyncio
@respx.mock
async def test_analytics_api_endpoint():
    """Verify POST /api/v1/analytics/trends HTTP endpoint."""
    respx.get("https://en.wikipedia.org/w/api.php").respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "123": {
                        "title": "Rust (programming language)",
                        "langlinks": [],
                    }
                }
            }
        },
    )
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/Rust_(programming_language)/monthly/2023010100/2023030100"
    ).respond(
        status_code=200,
        json={
            "items": [
                {"project": "en.wikipedia", "article": "Rust_(programming_language)", "granularity": "monthly", "timestamp": "2023010100", "views": 50000},
                {"project": "en.wikipedia", "article": "Rust_(programming_language)", "granularity": "monthly", "timestamp": "2023020100", "views": 55000},
                {"project": "en.wikipedia", "article": "Rust_(programming_language)", "granularity": "monthly", "timestamp": "2023030100", "views": 60000},
            ]
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/analytics/trends",
            json={
                "topic": "Rust (programming language)",
                "language_codes": ["en"],
                "start_date": "20230101",
                "end_date": "20230301",
                "granularity": "monthly",
                "include_ai_summary": True,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "Rust (programming language)"
    assert "en" in data["languages"]
    assert data["languages"]["en"]["metrics"]["total_views"] == 165000
    assert data["comparison"]["dominant_language"] == "en"
    assert data["ai_interpretation"]["direction"] == "growing"


@pytest.mark.asyncio
@respx.mock
async def test_natural_language_analytics_endpoint():
    """Verify POST /api/v1/analytics/natural-language parses query and returns 4-stage analytics."""
    from unittest.mock import patch
    from app.schemas.requests import WikipediaQueryParams

    mock_parsed_params = WikipediaQueryParams(
        base_topic="Artificial intelligence",
        source_topic="Штучний інтелект",
        language_codes=["en"],
        start_date="20230101",
        end_date="20230301",
        granularity="monthly",
    )

    respx.get("https://en.wikipedia.org/w/api.php").respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "99": {
                        "title": "Artificial intelligence",
                        "langlinks": [],
                    }
                }
            }
        },
    )
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/Artificial_intelligence/monthly/2023010100/2023030100"
    ).respond(
        status_code=200,
        json={
            "items": [
                {"project": "en.wikipedia", "article": "Artificial_intelligence", "granularity": "monthly", "timestamp": "2023010100", "views": 200000},
                {"project": "en.wikipedia", "article": "Artificial_intelligence", "granularity": "monthly", "timestamp": "2023020100", "views": 250000},
                {"project": "en.wikipedia", "article": "Artificial_intelligence", "granularity": "monthly", "timestamp": "2023030100", "views": 300000},
            ]
        },
    )

    transport = ASGITransport(app=app)
    with patch("app.api.analyze.parse_user_query_to_schema", return_value=mock_parsed_params):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/analytics/natural-language",
                json={
                    "query": "тренди штучного інтелекту за перший квартал 2023",
                    "include_ai_summary": True,
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["topic"] == "Artificial intelligence"
    assert data["source_topic"] == "Штучний інтелект"
    assert "en" in data["languages"]
    assert data["languages"]["en"]["metrics"]["total_views"] == 750000
    assert data["ai_interpretation"]["direction"] == "growing"

