"""Strategy Pattern implementations for single-topic trend analysis and cross-language comparisons."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from app.schemas.analytics import (
    ComparisonMetricsDTO,
    TimeSeriesPoint,
    TrendDirection,
    TrendMetricsDTO,
)


class BaseAnalyticsStrategy(ABC):
    """Abstract base strategy for computing metrics from standardized DataFrames."""

    @abstractmethod
    def analyze(
        self,
        df: pd.DataFrame,
        granularity: str = "monthly",
    ) -> Tuple[TrendMetricsDTO, List[TimeSeriesPoint]]:
        raise NotImplementedError


class TrendAnalysisStrategy(BaseAnalyticsStrategy):
    """Computes rolling averages, growth rates (MoM/YoY), volatility, and anomaly detection."""

    def analyze(
        self,
        df: pd.DataFrame,
        granularity: str = "monthly",
    ) -> Tuple[TrendMetricsDTO, List[TimeSeriesPoint]]:
        if df.empty:
            empty_metrics = TrendMetricsDTO(
                total_views=0,
                average_views=0.0,
                median_views=0.0,
                std_dev=0.0,
                volatility_score=0.0,
                trend_direction="stable",
                confidence_score=0.0,
            )
            return empty_metrics, []

        is_monthly = granularity.lower() == "monthly"
        window = 3 if is_monthly else 7

        views_series = df["views"].astype(float)
        rolling_mean = views_series.rolling(window=window, min_periods=1).mean()

        mean_val = float(views_series.mean())
        std_val = float(views_series.std(ddof=0)) if len(views_series) > 1 else 0.0

        if std_val > 1e-6:
            z_scores = (views_series - mean_val) / std_val
        else:
            z_scores = pd.Series(0.0, index=df.index)

        anomaly_mask = z_scores > 2.5
        anomaly_count = int(anomaly_mask.sum())

        time_series_points: List[TimeSeriesPoint] = []
        for idx, row in df.iterrows():
            z = float(z_scores.loc[idx])
            is_anom = bool(anomaly_mask.loc[idx])
            roll_val = float(rolling_mean.loc[idx]) if not pd.isna(rolling_mean.loc[idx]) else None

            time_series_points.append(
                TimeSeriesPoint(
                    date=str(row["date"]),
                    timestamp=str(row["timestamp"]),
                    views=int(row["views"]),
                    rolling_average=round(roll_val, 1) if roll_val is not None else None,
                    is_partial=bool(row["is_partial"]),
                    is_anomaly=is_anom,
                    z_score=round(z, 2),
                )
            )

        complete_df = df[~df["is_partial"]]
        eval_df = complete_df if not complete_df.empty else df

        mom_growth: Optional[float] = None
        yoy_growth: Optional[float] = None

        if len(eval_df) >= 2:
            latest_views = float(eval_df["views"].iloc[-1])
            prev_views = float(eval_df["views"].iloc[-2])
            if prev_views > 0:
                mom_growth = round(((latest_views - prev_views) / prev_views) * 100.0, 2)

        lag = 12 if is_monthly else 365
        if len(eval_df) > lag:
            latest_views = float(eval_df["views"].iloc[-1])
            year_ago_views = float(eval_df["views"].iloc[-(lag + 1)])
            if year_ago_views > 0:
                yoy_growth = round(((latest_views - year_ago_views) / year_ago_views) * 100.0, 2)

        total_views = int(views_series.sum())
        median_val = float(views_series.median())
        volatility_score = round(std_val / mean_val, 3) if mean_val > 0 else 0.0

        peak_idx = views_series.idxmax()
        peak_views = int(views_series.loc[peak_idx])
        peak_date = str(df.loc[peak_idx, "date"])

        trough_idx = views_series.idxmin()
        trough_views = int(views_series.loc[trough_idx])
        trough_date = str(df.loc[trough_idx, "date"])

        trend_direction: TrendDirection = "stable"
        n_points = len(views_series)
        if n_points >= 3 and mean_val > 0:
            x = np.arange(n_points)
            slope, _ = np.polyfit(x, views_series.values, 1)
            relative_slope = slope / mean_val

            if volatility_score > 0.8:
                trend_direction = "volatile"
            elif relative_slope > 0.03:
                trend_direction = "growing"
            elif relative_slope < -0.03:
                trend_direction = "declining"
            else:
                trend_direction = "stable"

        confidence = 1.0
        if n_points < 6:
            confidence -= 0.3
        elif n_points < 12:
            confidence -= 0.15

        if volatility_score > 0.6:
            confidence -= 0.25
        elif volatility_score > 0.3:
            confidence -= 0.1

        confidence -= min(anomaly_count * 0.08, 0.25)
        confidence_score = round(max(0.1, min(1.0, confidence)), 2)

        metrics = TrendMetricsDTO(
            total_views=total_views,
            average_views=round(mean_val, 1),
            median_views=round(median_val, 1),
            std_dev=round(std_val, 1),
            volatility_score=volatility_score,
            mom_growth_percent=mom_growth,
            yoy_growth_percent=yoy_growth,
            peak_date=peak_date,
            peak_views=peak_views,
            trough_date=trough_date,
            trough_views=trough_views,
            trend_direction=trend_direction,
            confidence_score=confidence_score,
            anomaly_count=anomaly_count,
        )

        return metrics, time_series_points


class ComparisonAnalysisStrategy:
    """Computes cross-language market comparison, relative attention shares, and correlations."""

    def compare(
        self,
        language_dfs: Dict[str, pd.DataFrame],
        language_metrics: Dict[str, TrendMetricsDTO],
    ) -> ComparisonMetricsDTO:
        if not language_dfs:
            return ComparisonMetricsDTO(dominant_language="en")

        total_by_lang: Dict[str, int] = {
            lang: int(df["views"].sum()) for lang, df in language_dfs.items()
        }

        grand_total = sum(total_by_lang.values())
        shares = {}
        for lang, count in total_by_lang.items():
            shares[lang] = round((count / grand_total * 100.0), 2) if grand_total > 0 else 0.0

        dominant_lang = max(total_by_lang, key=lambda k: total_by_lang[k])

        fastest_growing_lang: Optional[str] = None
        highest_growth = -float("inf")
        for lang, m in language_metrics.items():
            growth_val = m.yoy_growth_percent if m.yoy_growth_percent is not None else m.mom_growth_percent
            if growth_val is not None and growth_val > highest_growth:
                highest_growth = growth_val
                fastest_growing_lang = lang

        correlation_matrix: Dict[str, Dict[str, float]] = {}
        langs = list(language_dfs.keys())
        for l1 in langs:
            correlation_matrix[l1] = {}
            for l2 in langs:
                if l1 == l2:
                    correlation_matrix[l1][l2] = 1.0
                else:
                    s1 = language_dfs[l1]["views"]
                    s2 = language_dfs[l2]["views"]
                    combined = pd.concat([s1, s2], axis=1).dropna()
                    if len(combined) > 2 and combined.iloc[:, 0].std() > 0 and combined.iloc[:, 1].std() > 0:
                        corr_val = float(combined.iloc[:, 0].corr(combined.iloc[:, 1]))
                        correlation_matrix[l1][l2] = round(corr_val, 3)
                    else:
                        correlation_matrix[l1][l2] = 0.0

        return ComparisonMetricsDTO(
            dominant_language=dominant_lang,
            fastest_growing_language=fastest_growing_lang,
            language_shares_percent=shares,
            correlation_matrix=correlation_matrix,
        )
