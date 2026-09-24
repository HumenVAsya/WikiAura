---
name: wikipedia_skill
description: Stateless FastAPI microservice to fetch Wikipedia data, calculate trends (YoY/MoM), and generate a PDF report using Playwright.
---

# Wikipedia Trend Analysis Skill

Stateless FastAPI microservice designed to fetch page view statistics and revision metrics from the Wikipedia API, calculate Month-over-Month (MoM) and Year-over-Year (YoY) trends using `pandas` and `matplotlib`, and generate downloadable PDF reports using `Jinja2` and `Playwright`.

## Architecture & Technology Stack

- **Package Manager**: `uv`
- **Framework**: `FastAPI` + `uvicorn`
- **HTTP Client**: `httpx` (async Wikipedia REST API client)
- **Data Processing & Visualization**: `pandas`, `matplotlib`
- **PDF Generation Engine**: `Jinja2` (HTML templating) + `Playwright` (Headless Chromium PDF rendering)

## Project Structure

```
.
├── SKILL.md
├── Dockerfile
├── pyproject.toml
├── app/
│   ├── main.py
│   ├── api/
│   │   └── analyze.py
│   ├── schemas/
│   │   └── requests.py
│   ├── services/
│   │   ├── wikipedia.py
│   │   ├── analytics.py
│   │   └── report.py
│   └── templates/
│       └── report.html
```

## Getting Started

### Using Makefile

```bash
make install     # Install dependencies with uv and Playwright Chromium
make dev         # Run local development server (uvicorn --reload)
make up          # Build and start via Docker Compose
make down        # Stop Docker Compose container
make clean       # Remove __pycache__ artifacts
```

### Manual Commands

```bash
# Local development
uv sync
uv run playwright install --with-deps chromium
uv run uvicorn app.main:app --reload

# Docker Compose
docker compose up --build
```

