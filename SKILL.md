---
name: wikipedia_skill
description: Stateless FastAPI microservice and Model Context Protocol (MCP) tool to resolve multilingual Wikipedia articles and fetch per-article pageview trends across global language editions using structured parameters or natural language queries.
---

# WikiAura: Wikipedia Trend Analysis MCP Tool

Stateless FastAPI microservice and Model Context Protocol (MCP) tool designed to resolve localized Wikipedia article titles and retrieve per-article monthly and daily pageview metrics across multiple Wikipedia language editions via Wikimedia REST & Action APIs.

Features both direct structured parameter analysis and natural language query parsing via Google Gemini 3.8 Flash + `instructor`.

## Key Capabilities & Architecture

- **Multilingual Hub Resolution**: Dynamically resolves article titles starting from any language edition (English, Ukrainian, German, Polish, etc.), ensuring localized topics missing on English Wikipedia (e.g., local legislation, regional brands, cultural events) are discovered and analyzed accurately.
- **Smart Redirect & Search Fallback**: Automatically follows MediaWiki page redirects (`redirects=1`) and checks disambiguation pages (`pageprops.disambiguation`) with an intelligent search fallback (`action=query&list=search`).
- **Normalized Language Codes**: Automatically handles MediaWiki language code quirks, such as Norwegian Bokmål (`nb` in `langlinks` mapped to `no.wikipedia.org` in the Pageviews REST API).
- **Date Boundary Alignment & Partial Periods**: Normalizes mid-month dates for monthly granularity to prevent `400 Bad Request` errors from Wikimedia, detects ongoing months with `is_partial: true`, and respects the Wikimedia Pageviews historical limit (`2015-07-01`).
- **Controlled Concurrency**: Concurrency-controlled batch retrieval with `asyncio.Semaphore(5)` and rate pacing, enabling reliable data fetching for 100+ languages simultaneously without triggering HTTP 429 rate limits.

## Technology Stack

- **Package & Dependency Manager**: `uv`
- **Framework**: `FastAPI` + `uvicorn`
- **HTTP Client**: `httpx.AsyncClient` with Wikimedia-compliant `User-Agent` and Dependency Injection
- **Validation & Schemas**: `pydantic v2`
- **LLM Parsing**: Google Gemini (`gemini-3.8-flash` with fallbacks to `gemini-3.5-flash-lite` and `gemini-3.5-flash`) via `instructor`
- **Test Suite**: `pytest`, `pytest-asyncio`, `respx`

---

## API Endpoints

### 1. Natural Language Query Analysis (`POST /api/v1/analyze-topic`)

Accepts a raw natural language query in English, Ukrainian, or any language:

```bash
curl -X POST "http://localhost:8000/api/v1/analyze-topic" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "statistics across all of Europe on interest in artificial intelligence"
  }'
```

#### Response:
```json
{
  "status": "success",
  "query": "statistics across all of Europe on interest in artificial intelligence",
  "parsed_params": {
    "base_topic": "Artificial intelligence",
    "source_topic": "Artificial intelligence",
    "language_codes": [
      "en", "de", "fr", "es", "it", "pl", "uk", "nl", "cs", "pt",
      "sv", "ro", "el", "hu", "da", "fi", "sk", "bg", "hr", "sr",
      "no", "lt", "lv", "et", "sl"
    ],
    "start_date": "20250927",
    "end_date": "20260927",
    "granularity": "monthly"
  },
  "results": [
    {
      "language": "de",
      "article_title": "Künstliche Intelligenz",
      "article_slug": "K%C3%BCnstliche_Intelligenz",
      "found": true,
      "total_views": 410835,
      "items": [
        {
          "timestamp": "2025100100",
          "date": "2025-10",
          "views": 42100,
          "is_partial": false
        },
        {
          "timestamp": "2026090100",
          "date": "2026-09",
          "views": 5736,
          "is_partial": true
        }
      ]
    },
    {
      "language": "pl",
      "article_title": "Sztuczna inteligencja",
      "article_slug": "Sztuczna_inteligencja",
      "found": true,
      "total_views": 130833,
      "items": [
        {
          "timestamp": "2025100100",
          "date": "2025-10",
          "views": 12450,
          "is_partial": false
        }
      ]
    }
  ]
}
```

---

### 2. Direct Structured Query Analysis (`POST /api/v1/analyze`)

Allows direct querying with structured parameters without LLM parsing overhead:

```bash
curl -X POST "http://localhost:8000/api/v1/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "base_topic": "Intermittent fasting",
    "language_codes": ["pl", "cs", "de"],
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "granularity": "monthly"
  }'
```

---

### 3. Full 4-Stage Trend Analytics & AI Synthesis (`POST /api/v1/analytics/trends`)

Executes the complete 4-stage pipeline (Ingestion -> Gap-Free Standardization -> Compute Strategies -> AI Synthesis):

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/trends" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Coffee",
    "language_codes": ["en", "uk", "de", "pl"],
    "start_date": "20230101",
    "end_date": "20231231",
    "granularity": "monthly",
    "include_ai_summary": true
  }'
```

#### Response:
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
    "language_shares_percent": {
      "en": 78.4,
      "de": 12.1,
      "pl": 5.8,
      "uk": 3.7
    },
    "correlation_matrix": {
      "en": { "en": 1.0, "de": 0.84, "pl": 0.72, "uk": 0.65 }
    }
  },
  "ai_interpretation": {
    "trend_summary": "Steady positive interest expansion observed for 'Coffee' led by Wikipedia [en].",
    "direction": "growing",
    "confidence": "high",
    "seasonality_detected": true,
    "key_drivers": ["Annual YoY trajectory: +12.8%.", "Fastest growing language edition: [pl]."],
    "business_takeaway": "Sustained audience interest suggests strong organic demand and viable expansion potential."
  }
}
```

---

### 4. Natural Language Analytics (`POST /api/v1/analytics/natural-language`)

Accepts natural language queries, extracts topics/dates/languages, and runs the 4-stage analytics engine:

```bash
curl -X POST "http://localhost:8000/api/v1/analytics/natural-language" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Покажи тренди єПідтримки в Україні та Польщі за рік",
    "include_ai_summary": true
  }'
```

---

## Local Development & Testing

```bash
# Run test suite
uv run pytest -v

# Run local development server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run via Docker Compose
docker compose up -d
```
