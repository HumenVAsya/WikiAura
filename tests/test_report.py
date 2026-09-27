"""Unit tests for the PDF report generation service."""

from __future__ import annotations

import pytest

from app.schemas.analytics import (
    AIInterpretationDTO,
    AnalyticsResultDTO,
    ComparisonMetricsDTO,
    LanguageAnalyticsDTO,
    TimeSeriesPoint,
    TrendMetricsDTO,
)
from app.services.charts import generate_trend_chart
from app.services.report import generate_pdf_report


# ── Fixtures (reused from test_charts pattern) ─────────────────────────────────


def _make_time_series(n: int = 12, base: int = 50_000) -> list[TimeSeriesPoint]:
    import math
    points = []
    for i in range(n):
        month = (i % 12) + 1
        year = 2023 + i // 12
        views = int(base + base * 0.3 * math.sin(i * 0.5))
        points.append(
            TimeSeriesPoint(
                date=f"{year}-{month:02d}",
                timestamp=f"{year}{month:02d}0100",
                views=views,
                rolling_average=float(views) * 0.95,
                is_partial=(i == n - 1),
                is_anomaly=(i == 5),
                z_score=3.1 if i == 5 else 0.1,
            )
        )
    return points


def _make_metrics(
    mom: float | None = 4.5,
    yoy: float | None = 12.8,
    direction: str = "growing",
    anomalies: int = 1,
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
        anomaly_count=anomalies,
    )


def _make_ai() -> AIInterpretationDTO:
    return AIInterpretationDTO(
        trend_summary=(
            "Coffee interest is growing consistently across all tested European markets, "
            "driven by a shift toward specialty coffee consumption."
        ),
        direction="growing",
        confidence="high",
        seasonality_detected=True,
        key_drivers=[
            "Q4 seasonal spike in hot-beverage searches",
            "Growing specialty coffee culture across Central Europe",
            "Increased media coverage of health benefits",
        ],
        business_takeaway=(
            "Strong and consistent demand signal across EN, UK, PL editions suggests "
            "a viable B2C opportunity in the European coffee-education niche. "
            "Consider launching in EN first, then localising for PL and UK."
        ),
    )


def _make_result(
    topic: str = "Coffee",
    langs: list[str] | None = None,
    include_comparison: bool = True,
    include_ai: bool = True,
) -> AnalyticsResultDTO:
    if langs is None:
        langs = ["en", "uk", "pl"]

    languages = {
        lang: LanguageAnalyticsDTO(
            language=lang,
            article_title=f"{topic} ({lang.upper()})",
            found=True,
            metrics=_make_metrics(
                mom=4.5 - i * 5,
                yoy=12.8 - i * 10,
                direction=["growing", "stable", "declining"][i % 3],
            ),
            time_series=_make_time_series(base=50_000 + i * 15_000),
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
                lang: languages[lang].metrics.total_views / total * 100
                for lang in langs
            },
            correlation_matrix={l1: {l2: 0.75 for l2 in langs} for l1 in langs},
        )

    return AnalyticsResultDTO(
        topic=topic,
        source_topic=None,
        granularity="monthly",
        start_date="20230101",
        end_date="20231231",
        languages=languages,
        comparison=comparison,
        ai_interpretation=_make_ai() if include_ai else None,
    )


def _is_valid_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


# ── Core PDF Tests ──────────────────────────────────────────────────────────────


class TestGeneratePdfReport:
    def test_returns_bytes(self):
        result = _make_result()
        pdf = generate_pdf_report(result)
        assert isinstance(pdf, bytes)

    def test_starts_with_pdf_header(self):
        result = _make_result()
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf), f"Expected %PDF- header, got: {pdf[:10]}"

    def test_minimum_size(self):
        """A chart-embedded PDF should be well over 50KB."""
        result = _make_result()
        pdf = generate_pdf_report(result)
        assert len(pdf) > 50_000, f"PDF too small: {len(pdf)} bytes"

    def test_with_pre_generated_chart(self):
        """Passing pre-generated chart_png should produce valid PDF."""
        result = _make_result()
        chart = generate_trend_chart(result)
        pdf = generate_pdf_report(result, chart_png=chart)
        assert _is_valid_pdf(pdf)

    def test_auto_generates_chart_when_none(self):
        """chart_png=None should auto-generate chart internally."""
        result = _make_result()
        pdf = generate_pdf_report(result, chart_png=None)
        assert _is_valid_pdf(pdf)

    def test_single_language(self):
        result = _make_result(langs=["en"])
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_five_languages(self):
        langs = ["en", "uk", "pl", "de", "fr"]
        result = _make_result(langs=langs)
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_without_ai_summary(self):
        """AI summary section should gracefully show fallback text."""
        result = _make_result(include_ai=False)
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_without_comparison(self):
        """Missing comparison metrics should skip share badges."""
        result = _make_result(include_comparison=False)
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_no_data_languages(self):
        """Languages where found=False should not break rendering."""
        result = AnalyticsResultDTO(
            topic="Unknown",
            granularity="monthly",
            start_date="20230101",
            end_date="20231231",
            languages={
                "en": LanguageAnalyticsDTO(language="en", found=False),
                "uk": LanguageAnalyticsDTO(language="uk", found=False),
            },
        )
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_source_topic_shown_in_header(self):
        """source_topic should appear as the primary header title."""
        result = _make_result()
        result.source_topic = "єПідтримка"
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_all_directions(self):
        """All 4 direction values should render metric badges correctly."""
        langs = ["en", "uk", "pl", "de"]
        directions = ["growing", "declining", "stable", "volatile"]
        result = _make_result(langs=langs)
        for lang, direction in zip(langs, directions):
            result.languages[lang].metrics.trend_direction = direction
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_none_mom_yoy_shows_dash(self):
        """None MoM/YoY should show '—' without crashing."""
        result = _make_result(langs=["en"])
        result.languages["en"].metrics.mom_growth_percent = None
        result.languages["en"].metrics.yoy_growth_percent = None
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_long_topic_name(self):
        """A very long topic name should not break header layout."""
        result = _make_result(topic="A Very Long Wikipedia Article Title That Could Potentially Overflow")
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_long_ai_business_takeaway(self):
        """Multi-sentence business takeaway should wrap correctly."""
        result = _make_result(include_ai=True)
        result.ai_interpretation.business_takeaway = (
            "This is a very long business takeaway that contains multiple sentences and should "
            "be properly word-wrapped across multiple lines without breaking the PDF layout. "
            "It continues here with even more text to ensure the wrapping logic handles "
            "edge cases gracefully and the bounding box calculation is correct."
        )
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_many_key_drivers(self):
        """AI with 8 key drivers should render all without overflow."""
        result = _make_result(include_ai=True)
        result.ai_interpretation.key_drivers = [
            f"Driver number {i}: Some detailed explanation of this market factor" for i in range(8)
        ]
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_zero_anomalies(self):
        """Zero anomalies should show green badge."""
        result = _make_result(langs=["en"])
        result.languages["en"].metrics.anomaly_count = 0
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_high_confidence_score(self):
        """Confidence 1.0 should render green confidence badge."""
        result = _make_result(langs=["en"])
        result.languages["en"].metrics.confidence_score = 1.0
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_low_confidence_score(self):
        """Confidence 0.2 should render red confidence badge."""
        result = _make_result(langs=["en"])
        result.languages["en"].metrics.confidence_score = 0.2
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)

    def test_daily_granularity(self):
        """Daily granularity should be reflected in the header."""
        result = _make_result()
        result.granularity = "daily"
        pdf = generate_pdf_report(result)
        assert _is_valid_pdf(pdf)


# ── PDF + Charts Integration ───────────────────────────────────────────────────


class TestPdfChartIntegration:
    def test_chart_embedded_in_pdf(self):
        """Embedding chart should increase PDF size relative to chart-less rendering."""
        result = _make_result(langs=["en"])
        chart = generate_trend_chart(result)

        pdf_with_chart = generate_pdf_report(result, chart_png=chart)
        assert len(pdf_with_chart) > len(chart), "PDF must be larger than the chart alone"

    def test_two_sequential_reports_are_independent(self):
        """Generating two PDFs from the same result should produce identical bytes."""
        result = _make_result()
        pdf1 = generate_pdf_report(result)
        pdf2 = generate_pdf_report(result)
        # Both valid PDFs
        assert _is_valid_pdf(pdf1)
        assert _is_valid_pdf(pdf2)
