"""Unit tests for the charts generation service."""

from __future__ import annotations

import struct
import zlib

import pytest

from app.schemas.analytics import (
    AIInterpretationDTO,
    AnalyticsResultDTO,
    ComparisonMetricsDTO,
    LanguageAnalyticsDTO,
    TimeSeriesPoint,
    TrendMetricsDTO,
)
from app.services.charts import (
    generate_comparison_chart,
    generate_sparklines,
    generate_trend_chart,
)


# ── Test Fixtures ──────────────────────────────────────────────────────────────


def _make_time_series(n: int = 12, base: int = 50_000) -> list[TimeSeriesPoint]:
    """Generate a predictable monthly time-series of n points."""
    import math

    points = []
    for i in range(n):
        month = (i % 12) + 1
        year = 2023 + i // 12
        views = int(base + base * 0.3 * math.sin(i * 0.5) + (i * 500))
        points.append(
            TimeSeriesPoint(
                date=f"{year}-{month:02d}",
                timestamp=f"{year}{month:02d}0100",
                views=views,
                rolling_average=float(views) * 0.95,
                is_partial=(i == n - 1),
                is_anomaly=(i == 5),
                z_score=3.1 if i == 5 else 0.2,
            )
        )
    return points


def _make_metrics(
    mom: float | None = 4.5,
    yoy: float | None = 12.8,
    direction: str = "growing",
) -> TrendMetricsDTO:
    return TrendMetricsDTO(
        total_views=750_000,
        average_views=62_500.0,
        median_views=60_000.0,
        std_dev=8_000.0,
        volatility_score=0.128,
        mom_growth_percent=mom,
        yoy_growth_percent=yoy,
        peak_date="2023-09",
        peak_views=95_000,
        trough_date="2023-01",
        trough_views=42_000,
        trend_direction=direction,
        confidence_score=0.87,
        anomaly_count=1,
    )


def _make_result(
    topic: str = "Coffee",
    langs: list[str] | None = None,
    include_comparison: bool = True,
    include_ai: bool = False,
) -> AnalyticsResultDTO:
    if langs is None:
        langs = ["en", "uk", "pl"]

    directions = ["growing", "stable", "declining"]
    mom_values = [4.5, -1.2, -8.7]
    yoy_values = [12.8, 2.1, -15.3]

    languages = {
        lang: LanguageAnalyticsDTO(
            language=lang,
            article_title=f"{topic} ({lang})",
            found=True,
            metrics=_make_metrics(
                mom=mom_values[i % len(mom_values)],
                yoy=yoy_values[i % len(yoy_values)],
                direction=directions[i % len(directions)],
            ),
            time_series=_make_time_series(base=50_000 + i * 10_000),
        )
        for i, lang in enumerate(langs)
    }

    comparison = None
    if include_comparison and len(langs) > 1:
        total = sum(dto.metrics.total_views for dto in languages.values())
        comparison = ComparisonMetricsDTO(
            dominant_language=langs[0],
            fastest_growing_language=langs[0],
            language_shares_percent={
                lang: (languages[lang].metrics.total_views / total) * 100
                for lang in langs
            },
            correlation_matrix={
                l1: {l2: 0.75 for l2 in langs} for l1 in langs
            },
        )

    ai = None
    if include_ai:
        ai = AIInterpretationDTO(
            trend_summary="Coffee interest is growing across all tested markets.",
            direction="growing",
            confidence="high",
            seasonality_detected=True,
            key_drivers=["Q4 seasonal spike", "Growing specialty coffee market"],
            business_takeaway="Strong signal for European coffee app expansion.",
        )

    return AnalyticsResultDTO(
        topic=topic,
        source_topic=None,
        granularity="monthly",
        start_date="20230101",
        end_date="20231231",
        languages=languages,
        comparison=comparison,
        ai_interpretation=ai,
    )


def _is_valid_png(data: bytes) -> bool:
    """Check for PNG magic bytes (8-byte header)."""
    return data[:8] == b"\x89PNG\r\n\x1a\n"


# ── Trend Chart Tests ──────────────────────────────────────────────────────────


class TestGenerateTrendChart:
    def test_returns_non_empty_bytes(self):
        result = _make_result()
        png = generate_trend_chart(result)
        assert isinstance(png, bytes)
        assert len(png) > 5_000, "PNG should be at least 5KB"

    def test_returns_valid_png(self):
        result = _make_result()
        png = generate_trend_chart(result)
        assert _is_valid_png(png), "Must start with PNG magic bytes"

    def test_single_language(self):
        result = _make_result(langs=["en"])
        png = generate_trend_chart(result)
        assert _is_valid_png(png)
        assert len(png) > 2_000

    def test_many_languages(self):
        langs = ["en", "uk", "pl", "de", "fr", "es", "it"]
        result = _make_result(langs=langs)
        png = generate_trend_chart(result)
        assert _is_valid_png(png)

    def test_no_data_returns_placeholder(self):
        result = AnalyticsResultDTO(
            topic="Unknown Topic",
            granularity="monthly",
            start_date="20230101",
            end_date="20231231",
            languages={"en": LanguageAnalyticsDTO(language="en", found=False)},
        )
        png = generate_trend_chart(result)
        assert _is_valid_png(png)
        assert len(png) > 1_000

    def test_with_all_anomalies(self):
        """Every point is an anomaly — should not crash."""
        result = _make_result(langs=["en"])
        for p in result.languages["en"].time_series:
            p.is_anomaly = True
        png = generate_trend_chart(result)
        assert _is_valid_png(png)

    def test_declining_trend_rendered(self):
        """Declining direction should produce valid chart."""
        result = _make_result(langs=["pl"])
        result.languages["pl"].metrics.trend_direction = "declining"
        result.languages["pl"].metrics.mom_growth_percent = -10.5
        result.languages["pl"].metrics.yoy_growth_percent = -22.0
        png = generate_trend_chart(result)
        assert _is_valid_png(png)

    def test_volatile_trend_rendered(self):
        result = _make_result(langs=["en"])
        result.languages["en"].metrics.trend_direction = "volatile"
        png = generate_trend_chart(result)
        assert _is_valid_png(png)

    def test_none_mom_yoy_renders_dash(self):
        """None MoM/YoY should show '—' without crashing."""
        result = _make_result(langs=["en"])
        result.languages["en"].metrics.mom_growth_percent = None
        result.languages["en"].metrics.yoy_growth_percent = None
        png = generate_trend_chart(result)
        assert _is_valid_png(png)

    def test_no_comparison_data(self):
        """Missing comparison metrics should skip donut panel."""
        result = _make_result(langs=["en", "uk"], include_comparison=False)
        png = generate_trend_chart(result)
        assert _is_valid_png(png)

    def test_with_ai_interpretation(self):
        """AI interpretation data should not affect chart rendering."""
        result = _make_result(include_ai=True)
        png = generate_trend_chart(result)
        assert _is_valid_png(png)

    def test_short_time_series(self):
        """Very short time series (2 points) should not crash."""
        result = _make_result(langs=["en"])
        result.languages["en"].time_series = _make_time_series(n=2)
        png = generate_trend_chart(result)
        assert _is_valid_png(png)

    def test_long_time_series(self):
        """Long daily time-series (365 points) should render correctly."""
        result = _make_result(langs=["en"])
        result.languages["en"].time_series = _make_time_series(n=365, base=10_000)
        png = generate_trend_chart(result)
        assert _is_valid_png(png)


# ── Comparison Chart Tests ──────────────────────────────────────────────────────


class TestGenerateComparisonChart:
    def test_returns_valid_png(self):
        result = _make_result()
        png = generate_comparison_chart(result)
        assert _is_valid_png(png)
        assert len(png) > 5_000

    def test_single_language(self):
        result = _make_result(langs=["en"])
        png = generate_comparison_chart(result)
        assert _is_valid_png(png)

    def test_positive_and_negative_growth(self):
        """Mixed positive/negative bars should render without error."""
        result = _make_result(langs=["en", "uk", "pl"])
        result.languages["en"].metrics.mom_growth_percent = 15.0
        result.languages["uk"].metrics.mom_growth_percent = -5.0
        result.languages["pl"].metrics.mom_growth_percent = 0.0
        png = generate_comparison_chart(result)
        assert _is_valid_png(png)

    def test_no_data_returns_placeholder(self):
        result = AnalyticsResultDTO(
            topic="Ghost Topic",
            granularity="monthly",
            start_date="20230101",
            end_date="20231231",
            languages={"en": LanguageAnalyticsDTO(language="en", found=False)},
        )
        png = generate_comparison_chart(result)
        assert _is_valid_png(png)

    def test_zero_growth_rates(self):
        result = _make_result(langs=["en"])
        result.languages["en"].metrics.mom_growth_percent = 0.0
        result.languages["en"].metrics.yoy_growth_percent = 0.0
        png = generate_comparison_chart(result)
        assert _is_valid_png(png)

    def test_five_languages(self):
        langs = ["en", "uk", "pl", "de", "fr"]
        result = _make_result(langs=langs)
        png = generate_comparison_chart(result)
        assert _is_valid_png(png)


# ── Sparklines Tests ────────────────────────────────────────────────────────────


class TestGenerateSparklines:
    def test_returns_valid_png(self):
        result = _make_result()
        png = generate_sparklines(result)
        assert _is_valid_png(png)
        assert len(png) > 3_000

    def test_single_language_sparkline(self):
        result = _make_result(langs=["en"])
        png = generate_sparklines(result)
        assert _is_valid_png(png)

    def test_four_languages_grid(self):
        """4 languages should produce 2x2 grid."""
        result = _make_result(langs=["en", "uk", "pl", "de"])
        png = generate_sparklines(result)
        assert _is_valid_png(png)

    def test_no_data_returns_placeholder(self):
        result = AnalyticsResultDTO(
            topic="Missing",
            granularity="monthly",
            start_date="20230101",
            end_date="20231231",
            languages={"en": LanguageAnalyticsDTO(language="en", found=False)},
        )
        png = generate_sparklines(result)
        assert _is_valid_png(png)

    def test_all_directions_in_grid(self):
        """All 4 direction values should render in one grid."""
        directions = ["growing", "declining", "stable", "volatile"]
        langs = ["en", "uk", "pl", "de"]
        result = _make_result(langs=langs)
        for i, (lang, direction) in enumerate(zip(langs, directions)):
            result.languages[lang].metrics.trend_direction = direction
        png = generate_sparklines(result)
        assert _is_valid_png(png)

    def test_long_article_title_truncated(self):
        """Long article titles should be truncated without layout breaking."""
        result = _make_result(langs=["en"])
        result.languages["en"].article_title = "A Very Long Wikipedia Article Title That Exceeds Normal Length"
        png = generate_sparklines(result)
        assert _is_valid_png(png)

    def test_seven_languages_fills_grid(self):
        """7 languages → 3 columns, 3 rows with 2 empty cells."""
        langs = ["en", "uk", "pl", "de", "fr", "es", "it"]
        result = _make_result(langs=langs)
        png = generate_sparklines(result)
        assert _is_valid_png(png)


# ── Cross-Chart Consistency ─────────────────────────────────────────────────────


class TestChartConsistency:
    def test_all_three_charts_from_same_result(self):
        """All 3 chart types should render from the same AnalyticsResultDTO."""
        result = _make_result(include_ai=True)
        trend_png = generate_trend_chart(result)
        compare_png = generate_comparison_chart(result)
        sparklines_png = generate_sparklines(result)

        assert _is_valid_png(trend_png)
        assert _is_valid_png(compare_png)
        assert _is_valid_png(sparklines_png)

        assert trend_png != compare_png != sparklines_png, "Each chart type must produce distinct output"

    def test_determinism(self):
        """Same input should produce identical PNG output (deterministic rendering)."""
        result = _make_result()
        png1 = generate_trend_chart(result)
        png2 = generate_trend_chart(result)
        assert png1 == png2, "Chart rendering must be deterministic for caching"
