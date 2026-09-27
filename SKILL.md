---
name: wikipedia_skill
description: |
  WikiAura is a stateless FastAPI MCP tool for researching market interest using Wikipedia
  pageview trends. It resolves multilingual Wikipedia articles, fetches and analyzes pageview
  data across language editions, computes quantitative trend metrics (MoM, YoY, anomalies,
  cross-language correlation), generates AI executive synthesis, PNG charts, and PDF reports.
  Optimized for lightweight models (Claude Haiku, Gemini Flash).
---

# WikiAura: Wikipedia Trend Analysis MCP Tool

> **For AI Agents**: Read the [Agent Reasoning Guide](#agent-reasoning-guide) first.
> The complete machine-readable tool registry is at `GET /.well-known/mcp/tools`.

---

## What This Tool Does

WikiAura answers one core question: **"Is there real, measurable public interest in topic X across market Y?"**

It uses Wikipedia pageview data as a **free, neutral, and globally comparable proxy for information-seeking behaviour**. A spike in Wikipedia views for "Intermittent fasting" in Poland in 2023 is a genuine signal that the Polish-speaking market is actively researching this topic.

**Source**: Wikimedia REST API (`pageviews.wmcloud.org`) — updated daily, freely available.

---

## Key Capabilities

| Capability | Description |
|-----------|-------------|
| **Multilingual Hub Resolution** | Resolves topics from any language edition via MediaWiki langlinks |
| **Gap-Free Time Series** | Fills missing days/months with 0 — no gaps, always continuous |
| **Trend Metrics** | MoM%, YoY%, volatility (CV), Z-score anomaly detection |
| **Cross-Language Comparison** | Market share %, Pearson correlation matrix |
| **AI Synthesis** | Executive summary, key drivers, business takeaway via Gemini |
| **PNG Charts** | Dark-theme trend, comparison bar, and sparkline charts |
| **PDF Reports** | Single A4 page with chart + metrics + AI summary |
| **6-Hour Cache** | Repeat queries served instantly — no redundant API calls |
| **Partial Period Detection** | Current month marked `is_partial=true` |

---

## Agent Reasoning Guide

This section tells an AI agent **exactly how to decide which tool to call** for any user request.

### Decision Tree

```
User request received
        │
        ▼
Does the user ask for TRENDS / INTEREST / STATISTICS?
        │
       YES
        │
        ▼
Is the query in free-form natural language?
    ├── YES → call analyze_trends_nl
    └── NO  → call analyze_trends
        │
        ▼
Does the user also ask for a CHART / GRAPH / VISUAL?
    ├── YES → call generate_chart  (chart_type: "trend" by default)
    └── NO  → skip
        │
        ▼
Does the user ask for a PDF / REPORT / SHAREABLE DOCUMENT?
    ├── YES → call generate_report_pdf
    └── NO  → skip
        │
        ▼
Synthesize and present results to the user
```

### When to Use Each Tool

| Tool | Use When |
|------|----------|
| `analyze_trends` | You have a clear topic + language list. Best for structured queries. |
| `analyze_trends_nl` | User message is conversational / multilingual / ambiguous. |
| `generate_chart` | User mentions "chart", "graph", "plot", "show me visually". |
| `generate_report_pdf` | User asks for "PDF", "report", "something to share", "download". |
| `cache_stats` | Debugging, checking if results are cached. |
| `cache_invalidate` | User asks to "refresh", "reload", or "get fresh data" for a topic. |

### Language Code Selection Strategy

**Rule**: Start focused, expand only if asked.

| User says | Language codes |
|-----------|---------------|
| "in Ukraine" | `["uk"]` |
| "in Poland" | `["pl"]` |
| "in Central Europe" | `["pl", "cs", "sk", "hu", "de", "at"]` |
| "in Europe" | `["en", "de", "fr", "es", "it", "pl", "uk", "nl", "cs", "pt", "sv", "ro", "el", "hu", "da", "fi"]` |
| "globally" or "worldwide" | `["en", "zh", "es", "hi", "ar", "fr", "de", "ja", "pt", "ru"]` |
| "in English-speaking markets" | `["en"]` |
| No location mentioned | `["en"]` (default) |

Available region aliases (expand automatically): `europe`, `eastern_europe`, `latam`, `sea`, `mena`

### Date Range Selection Strategy

| User says | start_date | end_date |
|-----------|-----------|----------|
| "last year" | 1 year ago | today |
| "in 2023" | `20230101` | `20231231` |
| "last 2 years" | 2 years ago | today |
| "last 6 months" | 6 months ago | today |
| Not specified | 1 year ago (default) | today (default) |

**Hard constraint**: Wikimedia data starts `20150701`. Do not request dates before this.

### Granularity Selection

| Use case | granularity |
|----------|------------|
| Trend research, market analysis (default) | `monthly` |
| Viral spike detection, news events | `daily` |

### Interpreting Results

When you receive an `AnalyticsResultDTO`, present to the user:

1. **Lead with direction + confidence**: "Coffee interest in Poland is **growing** (YoY +14.2%, confidence: high)."
2. **Quote key metrics**: MoM%, YoY%, total views, peak date.
3. **Cross-language comparison**: Who leads? Fastest growing?
4. **AI business takeaway** (if available): Quote `ai_interpretation.business_takeaway` directly.
5. **Caveat**: Always mention that Wikipedia views reflect *information-seeking*, not *purchase intent*.
6. **Anomalies**: If `anomaly_count > 0`, note which months had spikes and consider external causes.
7. **Partial period**: If `is_partial=true` on the last data point, flag it as preliminary.

### Sample Reasoning Chain

**User**: "What is the trend for online courses in Poland and Czech Republic over the last 2 years?"

```
Step 1: Identify topic → "Online learning" (English Wikipedia title: "E-learning")
Step 2: Identify languages → ["pl", "cs"]
Step 3: Identify date range → last 2 years → start=2 years ago, end=today
Step 4: Granularity → monthly (trend research)
Step 5: Call analyze_trends(topic="E-learning", language_codes=["pl","cs"],
                            start_date="20240927", end_date="20260927",
                            granularity="monthly", include_ai_summary=true)
Step 6: Present metrics + AI summary
Step 7: Offer to generate chart if user wants visual
```

### Known Limitations (Always Disclose)

- Wikipedia views = **information-seeking behaviour**, NOT purchase intent or willingness to pay.
- Data starts **2015-07-01** — no historical data before that date.
- **Current month is partial** — `is_partial=true` on the last data point.
- Some niche topics or small language editions may return `found=false`.
- Non-English topics may have lower Wikipedia coverage than English-language equivalents.
- Cross-language correlation ≠ causation.

---

## API Endpoints Reference

### Core Analytics

#### `POST /api/v1/analytics/trends`
Full 4-stage analytics pipeline with structured parameters.

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/trends" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Coffee",
    "language_codes": ["en", "uk", "pl"],
    "start_date": "20230101",
    "end_date": "20231231",
    "granularity": "monthly",
    "include_ai_summary": true
  }'
```

**Response**: `AnalyticsResultDTO` (see schema below)

---

#### `POST /api/v1/analytics/natural-language`
Natural language query → full analytics pipeline.

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/natural-language" \
  -H "Content-Type: application/json" \
  -d '{"query": "Show coffee trends in Ukraine and Poland for the last year"}'
```

---

### Charts

#### `POST /api/v1/analytics/chart/trend` → `image/png`
Time-series rolling average + anomaly markers + market share donut.

#### `POST /api/v1/analytics/chart/compare` → `image/png`
3-panel bar chart: total views, MoM growth, YoY growth.

#### `POST /api/v1/analytics/chart/sparklines` → `image/png`
Compact sparkline grid, one mini-chart per language.

#### `POST /api/v1/analytics/chart/natural-language` → `image/png`
Natural language query → chart. Query parameter: `?chart_type=trend|compare|sparklines`

All chart endpoints accept the same `TrendAnalyticsRequest` body as `/analytics/trends`.

---

### PDF Reports

#### `POST /api/v1/analytics/report/pdf` → `application/pdf`
A4 PDF: header + chart + metric badges + AI summary + data quality + attribution.

#### `POST /api/v1/analytics/report/pdf/natural-language` → `application/pdf`
Natural language query → PDF report.

---

### Cache Management

#### `GET /api/v1/cache/stats` → `CacheStatsDTO`
Real-time cache statistics: hit rate, entries, memory, eviction count.

#### `POST /api/v1/cache/invalidate?topic=Coffee`
Remove all cached entries for a topic. Returns `{"entries_removed": N}`.

#### `POST /api/v1/cache/clear`
Clear entire cache and reset all counters.

---

### MCP Discovery

#### `GET /.well-known/mcp/tools` → `MCPManifest`
Full machine-readable tool registry in Anthropic/OpenAI tool format.

#### `GET /.well-known/mcp/tools/{tool_name}` → `MCPTool`
Single tool schema by name.

---

## AnalyticsResultDTO Schema

```json
{
  "topic": "Coffee",
  "source_topic": null,
  "granularity": "monthly",
  "start_date": "20230101",
  "end_date": "20231231",
  "languages": {
    "en": {
      "language": "en",
      "article_title": "Coffee",
      "found": true,
      "metrics": {
        "total_views": 1542000,
        "average_views": 128500.0,
        "median_views": 126400.0,
        "std_dev": 14200.0,
        "volatility_score": 0.11,
        "mom_growth_percent": 3.4,
        "yoy_growth_percent": 12.8,
        "peak_date": "2023-10",
        "peak_views": 149200,
        "trough_date": "2023-07",
        "trough_views": 110500,
        "trend_direction": "growing",
        "confidence_score": 0.95,
        "anomaly_count": 0
      },
      "time_series": [
        {
          "date": "2023-01",
          "timestamp": "2023010100",
          "views": 122000,
          "rolling_average": 122000.0,
          "is_partial": false,
          "is_anomaly": false,
          "z_score": -0.46
        }
      ]
    }
  },
  "comparison": {
    "dominant_language": "en",
    "fastest_growing_language": "pl",
    "language_shares_percent": {"en": 78.4, "pl": 12.1, "uk": 9.5},
    "correlation_matrix": {"en": {"pl": 0.84, "uk": 0.65}}
  },
  "ai_interpretation": {
    "trend_summary": "Steady positive interest for Coffee led by [en].",
    "direction": "growing",
    "confidence": "high",
    "seasonality_detected": true,
    "key_drivers": ["YoY +12.8%", "Fastest growing: [pl]"],
    "business_takeaway": "Strong organic demand across tested markets."
  }
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `trend_direction` | `growing\|declining\|stable\|volatile` | Directional classification |
| `confidence_score` | `0.0–1.0` | Statistical confidence (sample size × volatility) |
| `volatility_score` | `float` | Coefficient of variation (std/mean). > 0.5 = very volatile |
| `is_partial` | `bool` | True for current incomplete period |
| `is_anomaly` | `bool` | True if Z-score > 2.5 (statistical spike) |
| `confidence` | `high\|medium\|low` | AI confidence level |

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Framework | FastAPI + uvicorn |
| HTTP Client | httpx (async, Wikimedia User-Agent compliant) |
| Validation | pydantic v2 |
| LLM Parsing | Gemini 2.5 Flash + instructor (structured outputs) |
| Charts | matplotlib (dark theme, Agg backend) |
| PDF | fpdf2 (Arial Unicode TTF) |
| Cache | In-memory TTL+LRU (asyncio.Lock, 6h TTL, 256 entries) |
| Package Manager | uv |
| Tests | pytest + pytest-asyncio + respx |

---

## Local Development

```bash
# Start development server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run all tests
uv run pytest -v

# Run specific test suites
uv run pytest tests/test_analytics.py -v    # Analytics engine
uv run pytest tests/test_charts.py -v       # Chart generation
uv run pytest tests/test_report.py -v       # PDF reports
uv run pytest tests/test_cache.py -v        # Cache behaviour

# Docker
docker compose up -d
```

---

## Data Pipeline Architecture

```
User Query
    │
    ▼
[Stage 0] Cache Lookup (CacheKey hash)
    │ HIT → return instantly
    │ MISS ↓
    ▼
[Stage 1] Ingestion
    ├── LLM parse (NL query) or direct params
    ├── Wikimedia Action API → resolve article titles (langlinks)
    ├── Wikimedia REST API → fetch pageviews per language
    └── asyncio.Semaphore(5) concurrency control
    │
    ▼
[Stage 2] Validation & Standardization
    ├── Pydantic DTO validation
    ├── Gap-filling (missing dates → 0 views)
    ├── Rolling average (3-period monthly / 7-period daily)
    └── Partial period detection
    │
    ▼
[Stage 3] Computation
    ├── TrendAnalysisStrategy: MoM%, YoY%, volatility, Z-score, anomalies
    └── ComparisonAnalysisStrategy: market shares, Pearson correlation
    │
    ▼
[Stage 4] AI Synthesis (optional)
    └── Gemini: trend_summary, key_drivers, business_takeaway
    │
    ▼
[Stage 5] Cache Store → return AnalyticsResultDTO
```
