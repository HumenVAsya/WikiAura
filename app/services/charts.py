"""Chart generation service producing publication-ready PNG visualizations from AnalyticsResultDTO."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — no display required

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as ticker
from matplotlib.figure import Figure
import numpy as np

from app.schemas.analytics import AnalyticsResultDTO, LanguageAnalyticsDTO, TrendMetricsDTO


# ── Design System ──────────────────────────────────────────────────────────────

BACKGROUND = "#0d1117"
SURFACE = "#161b22"
BORDER = "#30363d"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED = "#484f58"
ACCENT = "#58a6ff"
SUCCESS = "#3fb950"
WARNING = "#d29922"
DANGER = "#f85149"

LANGUAGE_PALETTE = [
    "#58a6ff",  # blue
    "#3fb950",  # green
    "#d2a679",  # orange
    "#bc8cff",  # purple
    "#ff7b72",  # red
    "#79c0ff",  # light blue
    "#56d364",  # light green
    "#f2cc60",  # yellow
    "#ffa657",  # amber
    "#ff6e96",  # pink
]

DIRECTION_COLOR = {
    "growing": SUCCESS,
    "declining": DANGER,
    "volatile": WARNING,
    "stable": ACCENT,
}

FONT_FAMILY = "DejaVu Sans"

COMMON_STYLE = {
    "figure.facecolor": BACKGROUND,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": BORDER,
    "axes.labelcolor": TEXT_SECONDARY,
    "axes.titlecolor": TEXT_PRIMARY,
    "axes.grid": True,
    "grid.color": BORDER,
    "grid.linewidth": 0.6,
    "grid.alpha": 0.6,
    "xtick.color": TEXT_SECONDARY,
    "ytick.color": TEXT_SECONDARY,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "text.color": TEXT_PRIMARY,
    "legend.facecolor": SURFACE,
    "legend.edgecolor": BORDER,
    "legend.labelcolor": TEXT_SECONDARY,
    "legend.fontsize": 8,
    "font.family": FONT_FAMILY,
}


def _fig_to_bytes(fig: Figure) -> bytes:
    """Render a matplotlib Figure to PNG bytes and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _format_views(n: float) -> str:
    """Human-readable abbreviation for large numbers."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(int(n))


def _add_watermark(ax: plt.Axes, text: str = "Source: Wikimedia Pageviews API") -> None:
    """Place a subtle data-source watermark in the bottom-right corner."""
    ax.text(
        1.0, -0.08, text,
        transform=ax.transAxes,
        fontsize=7,
        color=TEXT_MUTED,
        ha="right",
        va="top",
    )


def _draw_metric_badge(ax: plt.Axes, x: float, y: float, label: str, value: str, color: str) -> None:
    """Draw a small label+value badge at normalized axes coordinates."""
    ax.text(x, y + 0.03, label, transform=ax.transAxes, fontsize=6.5, color=TEXT_SECONDARY, ha="center")
    ax.text(x, y, value, transform=ax.transAxes, fontsize=9.5, color=color, ha="center", fontweight="bold")


def generate_trend_chart(result: AnalyticsResultDTO) -> bytes:
    """Generate a multi-panel trend chart: time-series lines + market share donut.

    Layout:
    ┌────────────────────────────────┬────────────┐
    │  Time-series (rolling average) │  Donut     │
    │  + anomaly markers             │  % shares  │
    │  + confidence bands            │            │
    ├────────────────────────────────┴────────────┤
    │  Per-language metric badges (MoM, YoY, etc) │
    └─────────────────────────────────────────────┘
    """
    found_langs = {
        lang: dto for lang, dto in result.languages.items()
        if dto.found and dto.time_series and dto.metrics
    }
    if not found_langs:
        return _generate_no_data_chart(result.topic)

    with plt.rc_context(COMMON_STYLE):
        fig = plt.figure(figsize=(13, 7), facecolor=BACKGROUND)
        gs = gridspec.GridSpec(
            2, 2,
            figure=fig,
            width_ratios=[3, 1],
            height_ratios=[5, 1],
            hspace=0.08,
            wspace=0.25,
        )

        ax_main = fig.add_subplot(gs[0, 0])
        ax_donut = fig.add_subplot(gs[0, 1])
        ax_badges = fig.add_subplot(gs[1, :])
        ax_badges.axis("off")

        # ── Main Time-Series Panel ──────────────────────────────────────────
        for idx, (lang, dto) in enumerate(found_langs.items()):
            color = LANGUAGE_PALETTE[idx % len(LANGUAGE_PALETTE)]
            dates = [p.date for p in dto.time_series]
            raw_views = [p.views for p in dto.time_series]
            rolling = [p.rolling_average or p.views for p in dto.time_series]
            x = np.arange(len(dates))

            share = ""
            if result.comparison and lang in result.comparison.language_shares_percent:
                share = f" ({result.comparison.language_shares_percent[lang]:.1f}%)"

            ax_main.fill_between(x, raw_views, alpha=0.08, color=color)
            ax_main.plot(x, raw_views, linewidth=0.8, color=color, alpha=0.35, linestyle="--")
            ax_main.plot(x, rolling, linewidth=2.2, color=color, label=f"Wikipedia [{lang}]{share}", zorder=5)

            # Anomaly spikes
            anomaly_x = [i for i, p in enumerate(dto.time_series) if p.is_anomaly]
            anomaly_y = [rolling[i] for i in anomaly_x]
            if anomaly_x:
                ax_main.scatter(anomaly_x, anomaly_y, color=DANGER, s=55, zorder=10, marker="^",
                                linewidths=0.8, edgecolors=BACKGROUND, label=f"Spike [{lang}]" if idx == 0 else "")

            # Partial period marker
            partial_x = [i for i, p in enumerate(dto.time_series) if p.is_partial]
            if partial_x:
                ax_main.axvline(x=partial_x[0], color=WARNING, linewidth=0.8, linestyle=":", alpha=0.6)

        # X-axis: show only a manageable number of date labels
        n = len(dates)
        step = max(1, n // 8)
        ax_main.set_xticks(np.arange(0, n, step))
        ax_main.set_xticklabels(dates[::step], rotation=30, ha="right", fontsize=7.5)
        ax_main.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: _format_views(v)))
        ax_main.set_xlim(-0.5, n - 0.5)
        ax_main.set_title(
            f"{result.topic}  •  Wikipedia Pageview Trends  •  {result.start_date[:6]} → {result.end_date[:6]}",
            fontsize=11, color=TEXT_PRIMARY, pad=12, loc="left", fontweight="bold",
        )
        ax_main.set_ylabel("Pageviews (rolling avg)", fontsize=8.5, color=TEXT_SECONDARY)
        ax_main.legend(loc="upper left", framealpha=0.9, ncol=min(3, len(found_langs)))
        _add_watermark(ax_main)

        # ── Donut Chart — Market Share ──────────────────────────────────────
        if result.comparison and result.comparison.language_shares_percent:
            shares_map = {
                lang: result.comparison.language_shares_percent.get(lang, 0)
                for lang in found_langs
            }
            labels = list(shares_map.keys())
            sizes = list(shares_map.values())
            colors = [LANGUAGE_PALETTE[i % len(LANGUAGE_PALETTE)] for i in range(len(labels))]

            wedges, texts, autotexts = ax_donut.pie(
                sizes,
                labels=labels,
                colors=colors,
                autopct="%1.1f%%",
                pctdistance=0.72,
                startangle=90,
                wedgeprops={"linewidth": 1.5, "edgecolor": BACKGROUND},
                textprops={"fontsize": 7.5, "color": TEXT_SECONDARY},
            )
            for at in autotexts:
                at.set_fontsize(6.5)
                at.set_color(TEXT_PRIMARY)

            centre_circle = plt.Circle((0, 0), 0.52, fc=SURFACE)
            ax_donut.add_patch(centre_circle)
            ax_donut.set_title("Attention\nShare", fontsize=8.5, color=TEXT_SECONDARY, pad=6)
            dom = result.comparison.dominant_language
            ax_donut.text(0, 0, f"[{dom}]\nleads", ha="center", va="center",
                          fontsize=7.5, color=TEXT_PRIMARY, fontweight="bold")
        else:
            ax_donut.axis("off")

        # ── Metric Badges ───────────────────────────────────────────────────
        badge_step = 1.0 / (len(found_langs) + 1)
        for idx, (lang, dto) in enumerate(found_langs.items()):
            m: TrendMetricsDTO = dto.metrics
            color = LANGUAGE_PALETTE[idx % len(LANGUAGE_PALETTE)]
            bx = (idx + 1) * badge_step

            dir_color = DIRECTION_COLOR.get(m.trend_direction, ACCENT)
            mom_color = SUCCESS if (m.mom_growth_percent or 0) >= 0 else DANGER
            yoy_color = SUCCESS if (m.yoy_growth_percent or 0) >= 0 else DANGER

            mom_str = f"{m.mom_growth_percent:+.1f}%" if m.mom_growth_percent is not None else "—"
            yoy_str = f"{m.yoy_growth_percent:+.1f}%" if m.yoy_growth_percent is not None else "—"

            ax_badges.text(bx, 0.92, f"[{lang}]", transform=ax_badges.transAxes,
                           fontsize=8, color=color, ha="center", fontweight="bold")
            ax_badges.text(bx - 0.06, 0.55, "MoM", transform=ax_badges.transAxes,
                           fontsize=6.5, color=TEXT_SECONDARY, ha="center")
            ax_badges.text(bx - 0.06, 0.18, mom_str, transform=ax_badges.transAxes,
                           fontsize=9, color=mom_color, ha="center", fontweight="bold")
            ax_badges.text(bx, 0.55, "YoY", transform=ax_badges.transAxes,
                           fontsize=6.5, color=TEXT_SECONDARY, ha="center")
            ax_badges.text(bx, 0.18, yoy_str, transform=ax_badges.transAxes,
                           fontsize=9, color=yoy_color, ha="center", fontweight="bold")
            ax_badges.text(bx + 0.06, 0.55, "Direction", transform=ax_badges.transAxes,
                           fontsize=6.5, color=TEXT_SECONDARY, ha="center")
            ax_badges.text(bx + 0.06, 0.18, m.trend_direction.capitalize(), transform=ax_badges.transAxes,
                           fontsize=9, color=dir_color, ha="center", fontweight="bold")

        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        fig.text(0.5, -0.01, f"Generated by WikiAura  •  {generated_at}  •  Data: Wikimedia REST API",
                 ha="center", fontsize=7, color=TEXT_MUTED)

        return _fig_to_bytes(fig)


def generate_comparison_chart(result: AnalyticsResultDTO) -> bytes:
    """Generate a side-by-side bar chart comparing total views and growth rates across language editions.

    Layout:
    ┌──────────────────┬──────────────────┬──────────────────┐
    │  Total Views     │  MoM Growth %    │  YoY Growth %    │
    │  (bar chart)     │  (bar chart)     │  (bar chart)     │
    └──────────────────┴──────────────────┴──────────────────┘
    """
    found_langs = {
        lang: dto for lang, dto in result.languages.items()
        if dto.found and dto.metrics
    }
    if not found_langs:
        return _generate_no_data_chart(result.topic)

    with plt.rc_context(COMMON_STYLE):
        fig, axes = plt.subplots(1, 3, figsize=(13, 5), facecolor=BACKGROUND)

        langs = list(found_langs.keys())
        colors = [LANGUAGE_PALETTE[i % len(LANGUAGE_PALETTE)] for i in range(len(langs))]
        x = np.arange(len(langs))
        bar_width = 0.55

        # Panel 1: Total Views
        ax = axes[0]
        total_views = [dto.metrics.total_views for dto in found_langs.values()]
        bars = ax.bar(x, total_views, width=bar_width, color=colors, edgecolor=BACKGROUND, linewidth=1.2)
        for bar, val in zip(bars, total_views):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(total_views) * 0.01,
                    _format_views(val), ha="center", va="bottom", fontsize=8, color=TEXT_SECONDARY)
        ax.set_xticks(x)
        ax.set_xticklabels([f"[{l}]" for l in langs], fontsize=9)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: _format_views(v)))
        ax.set_title("Total Pageviews", fontsize=10, color=TEXT_PRIMARY, pad=10)
        ax.set_ylabel("Views", fontsize=8.5, color=TEXT_SECONDARY)

        # Panel 2: MoM Growth
        ax = axes[1]
        mom_values = [dto.metrics.mom_growth_percent or 0 for dto in found_langs.values()]
        bar_colors = [SUCCESS if v >= 0 else DANGER for v in mom_values]
        bars = ax.bar(x, mom_values, width=bar_width, color=bar_colors, edgecolor=BACKGROUND, linewidth=1.2)
        ax.axhline(0, color=BORDER, linewidth=1.0, linestyle="-")
        for bar, val in zip(bars, mom_values):
            sign = "+" if val >= 0 else ""
            ypos = bar.get_height() + 0.4 if val >= 0 else bar.get_height() - 1.5
            ax.text(bar.get_x() + bar.get_width() / 2, ypos,
                    f"{sign}{val:.1f}%", ha="center", va="bottom", fontsize=8, color=TEXT_SECONDARY)
        ax.set_xticks(x)
        ax.set_xticklabels([f"[{l}]" for l in langs], fontsize=9)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
        ax.set_title("Month-over-Month Growth", fontsize=10, color=TEXT_PRIMARY, pad=10)
        ax.set_ylabel("MoM %", fontsize=8.5, color=TEXT_SECONDARY)

        # Panel 3: YoY Growth
        ax = axes[2]
        yoy_values = [dto.metrics.yoy_growth_percent or 0 for dto in found_langs.values()]
        bar_colors = [SUCCESS if v >= 0 else DANGER for v in yoy_values]
        bars = ax.bar(x, yoy_values, width=bar_width, color=bar_colors, edgecolor=BACKGROUND, linewidth=1.2)
        ax.axhline(0, color=BORDER, linewidth=1.0, linestyle="-")
        for bar, val in zip(bars, yoy_values):
            sign = "+" if val >= 0 else ""
            ypos = bar.get_height() + 0.4 if val >= 0 else bar.get_height() - 1.5
            ax.text(bar.get_x() + bar.get_width() / 2, ypos,
                    f"{sign}{val:.1f}%", ha="center", va="bottom", fontsize=8, color=TEXT_SECONDARY)
        ax.set_xticks(x)
        ax.set_xticklabels([f"[{l}]" for l in langs], fontsize=9)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:+.0f}%"))
        ax.set_title("Year-over-Year Growth", fontsize=10, color=TEXT_PRIMARY, pad=10)
        ax.set_ylabel("YoY %", fontsize=8.5, color=TEXT_SECONDARY)

        fig.suptitle(
            f"Cross-Language Comparison  •  {result.topic}  •  {result.start_date[:6]} → {result.end_date[:6]}",
            fontsize=11, color=TEXT_PRIMARY, y=1.02, fontweight="bold",
        )
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        fig.text(0.5, -0.04, f"Generated by WikiAura  •  {generated_at}  •  Source: Wikimedia REST API",
                 ha="center", fontsize=7, color=TEXT_MUTED)
        try:
            fig.tight_layout(rect=[0, 0.02, 1, 1])
        except Exception:
            pass

        return _fig_to_bytes(fig)


def generate_sparklines(result: AnalyticsResultDTO) -> bytes:
    """Generate compact sparkline grid — one mini chart per language edition.

    Ideal for dashboards or embedding in a report alongside the PDF.
    Each cell shows: raw views sparkline + rolling average + direction arrow + key stats.
    """
    found_langs = {
        lang: dto for lang, dto in result.languages.items()
        if dto.found and dto.time_series and dto.metrics
    }
    if not found_langs:
        return _generate_no_data_chart(result.topic)

    n = len(found_langs)
    cols = min(n, 3)
    rows = (n + cols - 1) // cols

    with plt.rc_context(COMMON_STYLE):
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 4.5, rows * 2.8), facecolor=BACKGROUND)

        if n == 1:
            axes = [[axes]]
        elif rows == 1:
            axes = [axes]
        else:
            axes = axes.tolist()

        flat_axes = [ax for row in axes for ax in row]

        for idx, (lang, dto) in enumerate(found_langs.items()):
            ax: plt.Axes = flat_axes[idx]
            ax.set_facecolor(SURFACE)
            color = LANGUAGE_PALETTE[idx % len(LANGUAGE_PALETTE)]
            m = dto.metrics

            dates = [p.date for p in dto.time_series]
            raw = [p.views for p in dto.time_series]
            rolling = [p.rolling_average or p.views for p in dto.time_series]
            x = np.arange(len(dates))

            ax.fill_between(x, raw, alpha=0.1, color=color)
            ax.plot(x, raw, linewidth=0.6, color=color, alpha=0.4, linestyle="--")
            ax.plot(x, rolling, linewidth=2.0, color=color, zorder=5)

            # Anomaly dots
            for i, p in enumerate(dto.time_series):
                if p.is_anomaly:
                    ax.scatter(i, rolling[i], color=DANGER, s=30, zorder=10, marker="^")

            dir_color = DIRECTION_COLOR.get(m.trend_direction, ACCENT)
            dir_arrow = {"growing": "↑", "declining": "↓", "volatile": "⚡", "stable": "→"}
            arrow = dir_arrow.get(m.trend_direction, "→")

            title_parts = f"[{lang}]"
            if dto.article_title:
                title_parts += f"  {dto.article_title[:28]}"

            ax.set_title(title_parts, fontsize=8.5, color=color, pad=6, loc="left", fontweight="bold")

            mom_str = f"MoM {m.mom_growth_percent:+.1f}%" if m.mom_growth_percent is not None else "MoM —"
            yoy_str = f"YoY {m.yoy_growth_percent:+.1f}%" if m.yoy_growth_percent is not None else "YoY —"
            subtitle = f"{arrow} {m.trend_direction.capitalize()}  •  {_format_views(m.total_views)} total  •  {mom_str}  •  {yoy_str}"
            ax.text(0.0, 1.06, subtitle, transform=ax.transAxes,
                    fontsize=6.5, color=dir_color, ha="left")

            step = max(1, len(dates) // 4)
            ax.set_xticks(x[::step])
            ax.set_xticklabels(dates[::step], fontsize=6, rotation=25, ha="right")
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: _format_views(v)))
            ax.tick_params(axis="both", labelsize=6)

        # Hide unused subplots
        for idx in range(len(found_langs), len(flat_axes)):
            flat_axes[idx].axis("off")

        fig.suptitle(
            f"Sparklines  •  {result.topic}",
            fontsize=10, color=TEXT_PRIMARY, y=1.01, fontweight="bold",
        )
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
        fig.text(0.5, -0.02, f"WikiAura  •  {generated_at}  •  Source: Wikimedia REST API",
                 ha="center", fontsize=7, color=TEXT_MUTED)
        fig.tight_layout(rect=[0, 0.02, 1, 1])

        return _fig_to_bytes(fig)


def _generate_no_data_chart(topic: str) -> bytes:
    """Generate a placeholder chart when no data is available."""
    with plt.rc_context(COMMON_STYLE):
        fig, ax = plt.subplots(figsize=(8, 3), facecolor=BACKGROUND)
        ax.set_facecolor(SURFACE)
        ax.text(0.5, 0.55, "No Wikipedia data found", transform=ax.transAxes,
                ha="center", va="center", fontsize=14, color=TEXT_SECONDARY)
        ax.text(0.5, 0.35, f"Topic: {topic}", transform=ax.transAxes,
                ha="center", va="center", fontsize=10, color=TEXT_MUTED)
        ax.axis("off")
        return _fig_to_bytes(fig)
