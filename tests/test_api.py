import httpx
import pytest
import respx

from app.main import app


@pytest.mark.asyncio
async def test_healthz_endpoint():
    """Verify health check endpoint returns 200 healthy status."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "WikiAura"


@pytest.mark.asyncio
async def test_root_redirect_to_docs():
    """Verify GET / redirects to /docs."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/", follow_redirects=False)

    assert response.status_code in [302, 307]
    assert response.headers.get("location") == "/docs"


@pytest.mark.asyncio
async def test_analyze_validation_error_missing_fields():
    """Verify missing required fields return 422 Unprocessable Entity."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/analyze", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
@respx.mock
async def test_analyze_endpoint_success():
    """Verify POST /analyze end-to-end flow returning clean structured Wikipedia data via langlinks."""
    # Mock English Wikipedia langlinks resolver
    respx.get("https://en.wikipedia.org/w/api.php").respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "20104879": {
                        "pageid": 20104879,
                        "title": "Intermittent fasting",
                        "langlinks": [
                            {"lang": "pl", "*": "Post przerywany"},
                            {"lang": "cs", "*": "Přerušovaný půst"},
                        ],
                    }
                }
            }
        },
    )

    # Mock PL Pageviews
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/pl.wikipedia.org/all-access/user/Post_przerywany/monthly/2023010100/2023020100"
    ).respond(
        status_code=200,
        json={
            "items": [
                {"timestamp": "2023010100", "views": 10000},
                {"timestamp": "2023020100", "views": 15000},
            ]
        },
    )

    # Mock CS Pageviews
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/cs.wikipedia.org/all-access/user/Přerušovaný_půst/monthly/2023010100/2023020100"
    ).respond(
        status_code=200,
        json={
            "items": [
                {"timestamp": "2023010100", "views": 5000},
                {"timestamp": "2023020100", "views": 6000},
            ]
        },
    )

    payload = {
        "base_topic": "Intermittent fasting",
        "language_codes": ["pl", "cs"],
        "start_date": "2023-01-01",
        "end_date": "2023-02-01",
        "granularity": "monthly",
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["topic"] == "Intermittent fasting"
    assert data["languages_analyzed"] == ["pl", "cs"]
    assert len(data["results"]) == 2

    pl_res = next(r for r in data["results"] if r["language"] == "pl")
    assert pl_res["article_slug"] == "Post_przerywany"
    assert pl_res["article_title"] == "Post przerywany"
    assert pl_res["found"] is True
    assert pl_res["total_views"] == 25000
    assert len(pl_res["items"]) == 2
    assert pl_res["items"][0]["date"] == "2023-01"
    assert pl_res["items"][0]["views"] == 10000

    cs_res = next(r for r in data["results"] if r["language"] == "cs")
    assert cs_res["article_slug"] in ["Přerušovaný_půst", "P%C5%99eru%C5%A1ovan%C3%BD_p%C5%AFst"]
    assert cs_res["total_views"] == 11000


@pytest.mark.asyncio
@respx.mock
async def test_analyze_endpoint_topic_not_found():
    """Verify endpoint gracefully handles languages where no langlink is found."""
    respx.get("https://en.wikipedia.org/w/api.php").respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "-1": {
                        "ns": 0,
                        "title": "UnknownTopic9999",
                        "missing": "",
                    }
                }
            }
        },
    )

    payload = {
        "base_topic": "UnknownTopic9999",
        "language_codes": ["es"],
        "start_date": "2023-01-01",
        "end_date": "2023-02-01",
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["language"] == "es"
    assert data["results"][0]["found"] is False
    assert data["results"][0]["total_views"] == 0
    assert data["results"][0]["items"] == []


@pytest.mark.asyncio
@respx.mock
async def test_analyze_topic_endpoint_success():
    """Verify POST /api/v1/analyze-topic parses query via LLM and fetches Wikipedia data."""
    from unittest.mock import patch
    from app.schemas.requests import WikipediaQueryParams

    mock_parsed_params = WikipediaQueryParams(
        base_topic="Tobacco smoking",
        language_codes=["pl", "cs"],
        start_date="20230101",
        end_date="20230201",
        granularity="monthly",
    )

    # Mock English Wikipedia langlinks
    respx.get("https://en.wikipedia.org/w/api.php").respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "500": {
                        "pageid": 500,
                        "title": "Tobacco smoking",
                        "langlinks": [
                            {"lang": "pl", "*": "Palenie tytoniu"},
                            {"lang": "cs", "*": "Kouření"},
                        ],
                    }
                }
            }
        },
    )

    # Mock PL pageviews
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/pl.wikipedia.org/all-access/user/Palenie_tytoniu/monthly/2023010100/2023020100"
    ).respond(
        status_code=200,
        json={"items": [{"timestamp": "2023010100", "views": 8000}]},
    )

    # Mock CS pageviews
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/cs.wikipedia.org/all-access/user/Kou%C5%99en%C3%AD/monthly/2023010100/2023020100"
    ).respond(
        status_code=200,
        json={"items": [{"timestamp": "2023010100", "views": 6000}]},
    )

    transport = httpx.ASGITransport(app=app)
    with patch("app.api.analyze.parse_user_query_to_schema", return_value=mock_parsed_params):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze-topic",
                json={"query": "статистика по всій європі по людям які люблять курити"},
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["query"] == "статистика по всій європі по людям які люблять курити"
    assert data["parsed_params"]["base_topic"] == "Tobacco smoking"
    assert data["parsed_params"]["language_codes"] == ["pl", "cs"]
    assert len(data["results"]) == 2

    pl_item = next(r for r in data["results"] if r["language"] == "pl")
    assert pl_item["article_title"] == "Palenie tytoniu"
    assert pl_item["total_views"] == 8000

    cs_item = next(r for r in data["results"] if r["language"] == "cs")
    assert cs_item["article_title"] == "Kouření"
    assert cs_item["total_views"] == 6000

