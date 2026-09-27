"""PDF report generation service.

Produces a single A4-page, share-ready PDF report containing:
- Header: topic, date range, WikiAura branding
- Trend chart (embedded PNG)
- Key metrics grid: market share, MoM, YoY, direction, confidence
- AI executive summary
- Data quality section: confidence, anomalies, assumptions, limitations
- Footer: generation timestamp, Wikimedia attribution
"""

from __future__ import annotations

import io
import os
import textwrap
from datetime import datetime
from typing import Optional

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.schemas.analytics import (
    AIInterpretationDTO,
    AnalyticsResultDTO,
    ComparisonMetricsDTO,
    LanguageAnalyticsDTO,
    TrendMetricsDTO,
)
from app.services.charts import generate_trend_chart


FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app", "fonts")

# ── Design Tokens ─────────────────────────────────────────────────────────────

# All colours as (R, G, B) tuples
C_BG = (13, 17, 23)        # #0d1117
C_SURFACE = (22, 27, 34)   # #161b22
C_BORDER = (48, 54, 61)    # #30363d
C_TEXT = (230, 237, 243)   # #e6edf3
C_MUTED = (139, 148, 158)  # #8b949e
C_DIM = (72, 79, 88)       # #484f58

C_BLUE = (88, 166, 255)    # #58a6ff  — growing / accent
C_GREEN = (63, 185, 80)    # #3fb950  — positive
C_RED = (248, 81, 73)      # #f85149  — negative
C_ORANGE = (210, 153, 34)  # #d29922  — volatile / warning
C_WHITE = (230, 237, 243)  # text primary

DIRECTION_COLOR = {
    "growing": C_GREEN,
    "declining": C_RED,
    "volatile": C_ORANGE,
    "stable": C_BLUE,
}

LANG_COLORS = [
    C_BLUE,
    C_GREEN,
    (210, 166, 121),  # amber
    (188, 140, 255),  # purple
    (255, 123, 114),  # salmon
    (121, 192, 255),  # sky blue
    (86, 211, 100),   # lime
]

PAGE_W = 210  # A4 mm
PAGE_H = 297  # A4 mm
MARGIN = 14   # mm


# ── Helpers ───────────────────────────────────────────────────────────────────


def _format_views(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(int(n))


def _pct(v: Optional[float], fallback: str = "—") -> str:
    if v is None:
        return fallback
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def _wrap(text: str, width: int = 90) -> list[str]:
    """Word-wrap text into lines of at most `width` characters."""
    return textwrap.wrap(text, width=width) or [""]


# ── PDF Class ─────────────────────────────────────────────────────────────────


class WikiAuraPDF(FPDF):
    """Custom FPDF subclass with WikiAura dark-theme styling."""

    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Arial", style="",  fname=os.path.join(FONTS_DIR, "Arial.ttf"))
        self.add_font("Arial", style="B", fname=os.path.join(FONTS_DIR, "Arial-Bold.ttf"))
        self.add_font("Arial", style="I", fname=os.path.join(FONTS_DIR, "Arial-Italic.ttf"))
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(auto=True, margin=MARGIN)
        self.add_page()
        self.set_fill_color(*C_BG)
        self.rect(0, 0, PAGE_W, PAGE_H, style="F")

    # ── Low-level drawing helpers ─────────────────────────────────────────────

    def _set_text(self, r: int, g: int, b: int) -> None:
        self.set_text_color(r, g, b)

    def _rule(self, y_offset: float = 0, color: tuple = C_BORDER, thickness: float = 0.3) -> None:
        """Draw a full-width horizontal rule at current y + y_offset."""
        y = self.get_y() + y_offset
        self.set_draw_color(*color)
        self.set_line_width(thickness)
        self.line(MARGIN, y, PAGE_W - MARGIN, y)

    def _section_title(self, title: str) -> None:
        """Render a section header with accent underline."""
        self.ln(4)
        self._set_text(*C_BLUE)
        self.set_font("Arial", style="B", size=8)
        self.cell(0, 5, title.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._rule(y_offset=0.5, color=C_BORDER, thickness=0.2)
        self.ln(2)

    def _badge(
        self,
        x: float, y: float,
        label: str, value: str,
        value_color: tuple = C_WHITE,
        width: float = 36,
        height: float = 12,
    ) -> None:
        """Draw a metric badge: surface rectangle + label + value."""
        self.set_fill_color(*C_SURFACE)
        self.set_draw_color(*C_BORDER)
        self.set_line_width(0.2)
        self.rect(x, y, width, height, style="FD")

        # Label
        self.set_xy(x, y + 1.5)
        self.set_font("Arial", size=5.5)
        self._set_text(*C_MUTED)
        self.cell(width, 3, label, align="C")

        # Value
        self.set_xy(x, y + 5.5)
        self.set_font("Arial", style="B", size=9)
        self._set_text(*value_color)
        self.cell(width, 4, value, align="C")

    def _bullet(self, text: str, color: tuple = C_MUTED) -> None:
        """Render a bullet-point line."""
        self.set_font("Arial", size=7)
        self._set_text(*color)
        self.cell(5, 4.5, "-", align="C")
        # Indent + wrap long bullets
        lines = _wrap(text, width=95)
        for i, line in enumerate(lines):
            if i > 0:
                self.set_xy(MARGIN + 5, self.get_y() + 4.5)
            self.cell(0, 4.5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if i == 0 and len(lines) > 1:
                self.set_x(MARGIN + 5)

    def _body(self, text: str, color: tuple = C_TEXT, size: float = 7.5) -> None:
        self.set_font("Arial", size=size)
        self._set_text(*color)
        for line in _wrap(text, width=100):
            self.cell(0, 5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


# ── Main Public Function ──────────────────────────────────────────────────────


def generate_pdf_report(
    result: AnalyticsResultDTO,
    chart_png: Optional[bytes] = None,
) -> bytes:
    """Generate a complete A4 dark-theme PDF report.

    Args:
        result: The fully populated AnalyticsResultDTO from the analytics engine.
        chart_png: Optional pre-generated PNG bytes. If None, chart is generated
                   automatically from the result.

    Returns:
        PDF as bytes (starts with b'%PDF-').
    """
    if chart_png is None:
        chart_png = generate_trend_chart(result)

    pdf = WikiAuraPDF()

    _render_header(pdf, result)
    _render_chart(pdf, chart_png)
    _render_metrics_grid(pdf, result)
    _render_ai_summary(pdf, result.ai_interpretation)
    _render_data_quality(pdf, result)
    _render_footer(pdf, result)

    return bytes(pdf.output())


# ── Section Renderers ─────────────────────────────────────────────────────────


def _render_header(pdf: WikiAuraPDF, result: AnalyticsResultDTO) -> None:
    """Top header: logo text + topic + date range."""
    # Logo / brand
    pdf.set_font("Arial", style="B", size=18)
    pdf._set_text(*C_BLUE)
    pdf.cell(0, 10, "WikiAura", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Tagline
    pdf.set_font("Arial", size=7.5)
    pdf._set_text(*C_MUTED)
    pdf.cell(0, 4, "Wikipedia Pageview Trend Intelligence  |  Powered by Wikimedia REST API",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(2)
    pdf._rule(color=C_BORDER, thickness=0.4)
    pdf.ln(3)

    # Topic + period
    pdf.set_font("Arial", style="B", size=13)
    pdf._set_text(*C_TEXT)
    topic_display = result.source_topic or result.topic
    pdf.cell(0, 7, topic_display, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Arial", size=7.5)
    pdf._set_text(*C_MUTED)
    start = result.start_date[:6].replace("20", "20", 1)  # keep as-is
    end = result.end_date[:6]
    langs = ", ".join(
        f"[{lang}]" for lang in result.languages
        if result.languages[lang].found
    )
    pdf.cell(
        0, 5,
        f"Period: {start} to {end}   |   Granularity: {result.granularity}   |   Languages: {langs}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.ln(4)


def _render_chart(pdf: WikiAuraPDF, chart_png: bytes) -> None:
    """Embed the PNG chart into the PDF page."""
    chart_buf = io.BytesIO(chart_png)
    img_w = PAGE_W - 2 * MARGIN  # full content width
    # Calculate proportional height from 13:7 figure aspect ratio
    img_h = img_w * (7 / 13)

    pdf.image(chart_buf, x=MARGIN, y=pdf.get_y(), w=img_w, h=img_h)
    pdf.set_y(pdf.get_y() + img_h + 3)


def _render_metrics_grid(pdf: WikiAuraPDF, result: AnalyticsResultDTO) -> None:
    """Render a row of metric badges — one set per language."""
    found_langs = {
        lang: dto for lang, dto in result.languages.items()
        if dto.found and dto.metrics
    }
    if not found_langs:
        return

    pdf._section_title("Key Metrics by Language")

    n_langs = len(found_langs)
    badge_w = 36.0
    badge_h = 12.0
    gap = 3.0
    badges_per_lang = 4  # share, mom, yoy, direction
    total_badges_w = badges_per_lang * badge_w + (badges_per_lang - 1) * gap
    # How many languages fit per row
    row_w = PAGE_W - 2 * MARGIN
    langs_per_row = max(1, int(row_w // (total_badges_w + gap)))

    for row_start in range(0, n_langs, langs_per_row):
        row_langs = list(found_langs.items())[row_start: row_start + langs_per_row]
        base_y = pdf.get_y()

        for col_idx, (lang, dto) in enumerate(row_langs):
            m: TrendMetricsDTO = dto.metrics
            color = LANG_COLORS[
                list(found_langs.keys()).index(lang) % len(LANG_COLORS)
            ]

            # Language label above badges
            bx = MARGIN + col_idx * (total_badges_w + gap + 4)
            pdf.set_xy(bx, base_y)
            pdf.set_font("Arial", style="B", size=7.5)
            pdf._set_text(*color)
            pdf.cell(total_badges_w, 4.5, f"[{lang}]  {dto.article_title or ''}",
                     align="L", new_x=XPos.RIGHT, new_y=YPos.NEXT)

            lang_y = base_y + 5

            # Share badge
            share_val = "—"
            if result.comparison and lang in result.comparison.language_shares_percent:
                share_val = f"{result.comparison.language_shares_percent[lang]:.1f}%"
            pdf._badge(bx, lang_y, "ATTENTION SHARE", share_val, color)

            # MoM badge
            mom_color = C_GREEN if (m.mom_growth_percent or 0) >= 0 else C_RED
            pdf._badge(bx + badge_w + gap, lang_y, "MoM GROWTH", _pct(m.mom_growth_percent), mom_color)

            # YoY badge
            yoy_color = C_GREEN if (m.yoy_growth_percent or 0) >= 0 else C_RED
            pdf._badge(bx + 2 * (badge_w + gap), lang_y, "YoY GROWTH", _pct(m.yoy_growth_percent), yoy_color)

            # Direction badge
            dir_color = DIRECTION_COLOR.get(m.trend_direction, C_BLUE)
            dir_icons = {"growing": "↑", "declining": "↓", "volatile": "~", "stable": "→"}
            dir_text = f"{dir_icons.get(m.trend_direction, '')} {m.trend_direction.capitalize()}"
            pdf._badge(bx + 3 * (badge_w + gap), lang_y, "DIRECTION", dir_text, dir_color)

        # Move past the badges + gap
        pdf.set_y(base_y + 5 + badge_h + gap)

    pdf.ln(2)


def _render_ai_summary(pdf: WikiAuraPDF, ai: Optional[AIInterpretationDTO]) -> None:
    """Render the AI executive summary block."""
    pdf._section_title("AI Executive Summary")

    if ai is None:
        pdf.set_font("Arial", style="I", size=7.5)
        pdf._set_text(*C_MUTED)
        pdf.cell(0, 5, "AI synthesis not requested for this report.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        return

    # Overall direction + confidence pill
    dir_color = DIRECTION_COLOR.get(ai.direction, C_BLUE)
    conf_map = {"high": C_GREEN, "medium": C_ORANGE, "low": C_RED}
    conf_color = conf_map.get(ai.confidence, C_MUTED)

    pdf.set_font("Arial", style="B", size=7.5)
    pdf._set_text(*dir_color)
    pdf.cell(40, 5, f"Trend: {ai.direction.upper()}", new_x=XPos.RIGHT, new_y=YPos.TOP)
    pdf._set_text(*conf_color)
    pdf.cell(50, 5, f"Confidence: {ai.confidence.upper()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    # Summary paragraph
    pdf._body(ai.trend_summary, color=C_TEXT)
    pdf.ln(1)

    # Key drivers
    if ai.key_drivers:
        pdf.set_font("Arial", style="B", size=7)
        pdf._set_text(*C_MUTED)
        pdf.cell(0, 4.5, "Key Drivers:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for driver in ai.key_drivers:
            pdf._bullet(driver, color=C_TEXT)

    # Business takeaway box
    pdf.ln(2)
    box_x = MARGIN
    box_y = pdf.get_y()
    box_w = PAGE_W - 2 * MARGIN
    # Estimate box height from wrapped text
    lines = _wrap(ai.business_takeaway, width=100)
    box_h = 6 + len(lines) * 4.5

    pdf.set_fill_color(*C_SURFACE)
    pdf.set_draw_color(*C_BLUE)
    pdf.set_line_width(0.3)
    pdf.rect(box_x, box_y, box_w, box_h, style="FD")

    # Left accent bar
    pdf.set_fill_color(*C_BLUE)
    pdf.rect(box_x, box_y, 1.5, box_h, style="F")

    pdf.set_xy(box_x + 3, box_y + 2)
    pdf.set_font("Arial", style="B", size=7)
    pdf._set_text(*C_BLUE)
    pdf.cell(0, 4, ">> BUSINESS TAKEAWAY", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(box_x + 3)
    for line in lines:
        pdf.set_font("Arial", size=7.5)
        pdf._set_text(*C_TEXT)
        pdf.cell(box_w - 5, 4.5, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_x(box_x + 3)

    pdf.set_y(box_y + box_h + 3)


def _render_data_quality(pdf: WikiAuraPDF, result: AnalyticsResultDTO) -> None:
    """Render data quality, anomalies, assumptions, and limitations section."""
    pdf._section_title("Data Quality & Limitations")

    found_langs = {
        lang: dto for lang, dto in result.languages.items()
        if dto.found and dto.metrics
    }

    # Stats row
    total_anomalies = sum(dto.metrics.anomaly_count for dto in found_langs.values())
    avg_confidence = (
        sum(dto.metrics.confidence_score for dto in found_langs.values()) / len(found_langs)
        if found_langs else 0.0
    )
    partial_count = sum(
        1 for dto in found_langs.values()
        if any(p.is_partial for p in dto.time_series)
    )

    pdf.set_font("Arial", size=7)
    pdf._set_text(*C_MUTED)
    conf_color = C_GREEN if avg_confidence >= 0.8 else C_ORANGE if avg_confidence >= 0.5 else C_RED
    anomaly_color = C_RED if total_anomalies > 0 else C_GREEN

    badge_y = pdf.get_y()
    pdf._badge(MARGIN, badge_y, "AVG CONFIDENCE", f"{avg_confidence:.0%}", conf_color, width=42)
    pdf._badge(MARGIN + 45, badge_y, "ANOMALIES DETECTED", str(total_anomalies), anomaly_color, width=42)
    pdf._badge(MARGIN + 90, badge_y, "PARTIAL PERIODS", str(partial_count), C_ORANGE if partial_count > 0 else C_GREEN, width=42)
    pdf._badge(MARGIN + 135, badge_y, "LANGUAGES", str(len(found_langs)), C_BLUE, width=42)
    pdf.set_y(badge_y + 14)

    # Assumptions
    pdf.ln(1)
    assumptions = [
        "Wikipedia pageviews reflect public information-seeking behaviour, not purchase intent or willingness to pay.",
        "Wikimedia data available from 2015-07-01 for monthly and 2015-07-01 for daily granularity.",
        f"Current period ({result.end_date[:6]}) may be partial — metrics are approximate until the month closes.",
        "Cross-language correlation does not imply causal relationship between market interest levels.",
        "Rolling average uses 3-period window (monthly) or 7-period window (daily) to smooth noise.",
    ]
    pdf.set_font("Arial", style="B", size=7)
    pdf._set_text(*C_MUTED)
    pdf.cell(0, 4.5, "Assumptions & Limitations:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    for assumption in assumptions:
        pdf._bullet(assumption)

    pdf.ln(1)


def _render_footer(pdf: WikiAuraPDF, result: AnalyticsResultDTO) -> None:
    """Render the bottom attribution footer."""
    # Draw rule above footer
    pdf._rule(color=C_BORDER, thickness=0.25)
    pdf.ln(2)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    pdf.set_font("Arial", size=6.5)
    pdf._set_text(*C_DIM)
    pdf.cell(
        0, 4,
        f"Generated by WikiAura  |  {generated_at}  |  Source: Wikimedia REST API (pageviews.wmcloud.org)",
        align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
    pdf.cell(
        0, 4,
        "Data is freely available under CC0 1.0 Universal  |  https://wikimedia.org/api/rest_v1/",
        align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )
