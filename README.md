# WikiAura 🔍

> **Wikipedia Pageview Trend Intelligence** — MCP-compatible research tool for B2C founders and product teams.

[![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/Tests-134%20passed-brightgreen?logo=pytest)](./tests)
[![License](https://img.shields.io/badge/License-MIT-yellow)](./LICENSE)

---

## The Problem

B2C teams constantly face the same question before investing months of development:

> _"Is there real demand for this topic in this market right now?"_

Common approaches are either expensive (market research agencies), unreliable (gut feeling), or hard to use (raw Google Trends with no API). There is no lightweight, programmatic, multilingual tool to quickly validate market interest across different countries.

---

## The Solution

WikiAura uses **Wikipedia pageview data** as a free, neutral, globally comparable proxy for information-seeking behaviour.

When 50,000 people read the Polish Wikipedia article about "Intermittent fasting" in Q4 2023 — that's a real, measurable signal of growing market interest. WikiAura fetches, normalizes, analyzes, and visualizes this data in seconds.

**One API call gives you:**
- Month-over-month and year-over-year growth rates
- Cross-language market share and correlation
- Anomaly detection (viral spikes / crashes)
- AI executive summary with business takeaway
- PNG chart ready for a presentation
- A4 PDF report ready to share

---

## How It Works — 5-Stage Pipeline

```
User Query (natural language or structured)
        │
        ▼
┌─────────────────────────────────────────┐
│  Stage 0: Cache Lookup (TTL 6h, LRU)   │ ← instant on repeat queries
└───────────────────┬─────────────────────┘
                    │ MISS
                    ▼
┌─────────────────────────────────────────┐
│  Stage 1: Ingestion                     │
│  • Wikimedia Action API → resolve       │
│    article titles across 300+ languages │
│  • Wikimedia REST API → fetch pageviews │
│  • asyncio.Semaphore(5) concurrency     │
│  • Exponential backoff retry (429/5xx)  │
└───────────────────┬─────────────────────┘
                    ▼
┌─────────────────────────────────────────┐
│  Stage 2: Standardization               │
│  • Pydantic DTO validation              │
│  • Gap-filling: missing dates → 0       │
│  • Rolling average (3-month window)     │
│  • Partial period detection             │
└───────────────────┬─────────────────────┘
                    ▼
┌─────────────────────────────────────────┐
│  Stage 3: Computation                   │
│  • MoM %, YoY % growth                 │
│  • Volatility score (CV = std/mean)     │
│  • Z-score anomaly detection            │
│  • Cross-language Pearson correlation   │
│  • Market share % per language          │
└───────────────────┬─────────────────────┘
                    ▼
┌─────────────────────────────────────────┐
│  Stage 4: AI Synthesis (Gemini)         │
│  • trend_summary                        │
│  • key_drivers                          │
│  • business_takeaway                    │
└───────────────────┬─────────────────────┘
                    ▼
            AnalyticsResultDTO
         (JSON / PNG chart / PDF)
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Multilingual** | Resolves article titles across 300+ Wikipedia language editions automatically |
| **Natural Language** | `"Покажи тренди кави в Україні за 2023"` → full analytics |
| **Smart Redirect** | Follows MediaWiki redirects, disambiguation pages, search fallback |
| **Gap-Free Series** | Missing data points filled with 0 — always continuous time series |
| **Anomaly Detection** | Z-score based spike/crash detection with `is_anomaly` flag |
| **AI Summary** | Gemini generates executive summary + business takeaway |
| **PNG Charts** | Trend chart, comparison bar, sparklines grid — dark theme |
| **PDF Report** | Single A4 page with embedded chart, metric badges, AI summary |
| **6h Cache** | Repeat queries served instantly, LRU eviction at 256 entries |
| **Retry Logic** | Exponential backoff for HTTP 429/5xx with Retry-After header support |
| **MCP Compatible** | `GET /.well-known/mcp/tools` — auto-discovery by AI agents |

---

## Quick Start

### Prerequisites

```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repo
git clone https://github.com/HumenVAsya/WikiAura.git
cd WikiAura

# Copy environment variables
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

### Run locally

```bash
uv run uvicorn app.main:app --reload --port 8000
```

### Run with Docker

```bash
make up
# or
docker compose up --build
```

Server starts at `http://localhost:8000`
Swagger UI at `http://localhost:8000/docs`

---

## API Examples

### Natural language → JSON analytics

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/natural-language" \
  -H "Content-Type: application/json" \
  -d '{"query": "Coffee trends in Ukraine and Poland for 2023"}'
```

### Structured → PDF report

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/report/pdf" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Intermittent fasting",
    "language_codes": ["pl", "uk", "cs", "de"],
    "start_date": "20230101",
    "end_date": "20231231",
    "granularity": "monthly",
    "include_ai_summary": true
  }' \
  --output report.pdf && open report.pdf
```

### Natural language → PDF (simplest)

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/report/pdf/natural-language" \
  -H "Content-Type: application/json" \
  -d '{"query": "Тренди кетогенної дієти в Польщі та Чехії за 2023 рік"}' \
  --output report.pdf && open report.pdf
```

### Trend chart → PNG

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/chart/trend" \
  -H "Content-Type: application/json" \
  -d '{"topic": "Coffee", "language_codes": ["en", "uk", "pl"]}' \
  --output chart.png && open chart.png
```

---

## API Reference

### Analytics

| Method | Endpoint | Returns |
|--------|----------|---------|
| POST | `/api/v1/analytics/trends` | `AnalyticsResultDTO` (JSON) |
| POST | `/api/v1/analytics/natural-language` | `AnalyticsResultDTO` (JSON) |

### Charts

| Method | Endpoint | Returns |
|--------|----------|---------|
| POST | `/api/v1/analytics/chart/trend` | `image/png` — time series + anomalies + share donut |
| POST | `/api/v1/analytics/chart/compare` | `image/png` — 3-panel: views / MoM / YoY |
| POST | `/api/v1/analytics/chart/sparklines` | `image/png` — mini-chart grid per language |
| POST | `/api/v1/analytics/chart/natural-language` | `image/png` — NL query → chart |

### Reports

| Method | Endpoint | Returns |
|--------|----------|---------|
| POST | `/api/v1/analytics/report/pdf` | `application/pdf` |
| POST | `/api/v1/analytics/report/pdf/natural-language` | `application/pdf` |

### Cache

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/cache/stats` | Hit rate, entries, memory usage |
| POST | `/api/v1/cache/invalidate?topic=Coffee` | Remove cached topic |
| POST | `/api/v1/cache/clear` | Clear all + reset counters |

### MCP (AI Agent Discovery)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/.well-known/mcp/tools` | Full tool manifest (Anthropic/OpenAI format) |
| GET | `/.well-known/mcp/tools/{name}` | Single tool schema |

---

## Response Schema

```json
{
  "topic": "Coffee",
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
        "mom_growth_percent": 3.4,
        "yoy_growth_percent": 12.8,
        "trend_direction": "growing",
        "confidence_score": 0.95,
        "anomaly_count": 0
      },
      "time_series": [
        {
          "date": "2023-01",
          "views": 122000,
          "rolling_average": 118400.0,
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
    "language_shares_percent": {"en": 78.4, "pl": 12.1, "uk": 9.5}
  },
  "ai_interpretation": {
    "trend_summary": "Steady positive interest...",
    "direction": "growing",
    "confidence": "high",
    "key_drivers": ["YoY +12.8%", "Fastest growing: [pl]"],
    "business_takeaway": "Strong organic demand..."
  }
}
```

---

## Language Codes & Region Aliases

Use ISO 639-1 codes: `en`, `uk`, `pl`, `de`, `fr`, `cs`, `sk`, `hu` ...

Or region aliases that auto-expand:

| Alias | Expands to |
|-------|-----------|
| `europe` | 16 major European languages |
| `eastern_europe` | PL, CS, SK, HU, RO, BG, HR, SR, UK |
| `latam` | ES, PT, and Latin American variants |
| `sea` | South-East Asian languages |
| `mena` | Middle East & North Africa |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI + uvicorn |
| HTTP Client | httpx (async) |
| Validation | Pydantic v2 |
| LLM | Google Gemini via `instructor` |
| Charts | matplotlib (Agg backend, dark theme) |
| PDF | fpdf2 + Arial Unicode TTF |
| Cache | In-memory TTL+LRU (asyncio.Lock) |
| Package Manager | uv |
| Testing | pytest + pytest-asyncio + respx |
| Deploy | Docker Compose |

---

## Testing

```bash
# Run all tests
uv run pytest -v

# Run specific suites
uv run pytest tests/test_cache.py -v      # Cache: TTL, LRU, concurrency
uv run pytest tests/test_charts.py -v     # Charts: PNG validity, dark theme
uv run pytest tests/test_report.py -v     # PDF: header, size, edge cases
uv run pytest tests/test_retry.py -v      # Retry: backoff, Retry-After, errors
uv run pytest tests/test_mcp.py -v        # MCP: manifest, Anthropic/OpenAI compat
```

**134 / 134 tests passing ✅**

---

## Known Limitations

- Wikipedia views = **information-seeking behaviour**, not purchase intent
- Historical data starts **2015-07-01** — no earlier dates available
- Current incomplete month is marked `is_partial: true`
- Some niche topics in small language editions may return `found: false`
- Cache is in-memory — resets on container restart (Redis planned for v2)

---

## Roadmap

- [ ] **Web UI** — SPA with query input, chart preview, PDF download
- [ ] **Authentication** — API keys, usage tiers (Free / Pro / Team)
- [ ] **Scheduled Reports** — weekly/monthly digest for watchlisted topics
- [ ] **Topic Watchlist** — alert when trend changes significantly
- [ ] **Redis Cache** — persistent cache across restarts
- [ ] **Google Trends overlay** — second data source for validation
- [ ] **CSV Export** — raw data for analysts

---

## Data Source

All data comes from the **Wikimedia REST API** (`pageviews.wmcloud.org`):
- Free and open (Wikimedia Foundation)
- Updated daily
- Available since 2015-07-01
- Covers 300+ Wikipedia language editions
- No authentication required for reasonable usage

---

## License

MIT © WikiAura
