import httpx
import pytest
import respx

from app.services.wikipedia import (
    USER_AGENT,
    align_date_for_pageviews,
    create_wikimedia_client,
    fetch_all_languages_data,
    format_date_for_pageviews,
    format_period_label,
    get_pageviews,
    is_current_period,
    resolve_localized_titles,
    search_article_title_fallback,
)


def test_format_date_for_pageviews():
    """Verify standard date strings are converted to Wikimedia YYYYMMDD00 format."""
    assert format_date_for_pageviews("2023-01-01") == "2023010100"
    assert format_date_for_pageviews("2023-12-31") == "2023123100"
    assert format_date_for_pageviews("2023050100") == "2023050100"


def test_format_period_label():
    """Verify raw Wikimedia timestamps are formatted to clean date strings."""
    assert format_period_label("2023010100", granularity="monthly") == "2023-01"
    assert format_period_label("2023011500", granularity="daily") == "2023-01-15"
    assert format_period_label("short", granularity="monthly") == "short"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_localized_titles_success():
    """Test resolving localized titles via English Wikipedia Action API with prop=langlinks."""
    topic = "Intermittent fasting"
    languages = ["pl", "cs"]
    url = "https://en.wikipedia.org/w/api.php"

    mock_route = respx.get(url).respond(
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

    async with create_wikimedia_client() as client:
        titles = await resolve_localized_titles(client, base_topic=topic, language_codes=languages)

    assert titles == {"pl": "Post przerywany", "cs": "Přerušovaný půst"}
    assert mock_route.called
    request = mock_route.calls.last.request
    assert request.headers.get("user-agent") == USER_AGENT
    assert "prop=langlinks" in str(request.url)
    assert "titles=Intermittent+fasting" in str(request.url) or "titles=Intermittent fasting" in str(request.url)


@pytest.mark.asyncio
@respx.mock
async def test_resolve_localized_titles_missing_page():
    """Test resolution returns None for languages when page is missing on English Wikipedia."""
    topic = "NonexistentTopicXYZ123"
    languages = ["pl", "cs"]
    url = "https://en.wikipedia.org/w/api.php"

    respx.get(url).respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "-1": {
                        "ns": 0,
                        "title": "NonexistentTopicXYZ123",
                        "missing": "",
                    }
                }
            }
        },
    )

    async with create_wikimedia_client() as client:
        titles = await resolve_localized_titles(client, base_topic=topic, language_codes=languages)

    assert titles == {"pl": None, "cs": None}


@pytest.mark.asyncio
@respx.mock
async def test_resolve_localized_titles_http_error():
    """Test resolution handles 500 error gracefully returning None for all languages."""
    topic = "Error Topic"
    languages = ["de"]
    url = "https://en.wikipedia.org/w/api.php"

    respx.get(url).respond(status_code=500)

    async with create_wikimedia_client() as client:
        titles = await resolve_localized_titles(client, base_topic=topic, language_codes=languages)

    assert titles == {"de": None}


@pytest.mark.asyncio
@respx.mock
async def test_get_pageviews_success():
    """Test fetching pageviews returns parsed PageviewItem records with correct dates and user-agent."""
    lang = "pl"
    slug = "Post_przerywany"
    start_date = "2023-01-01"
    end_date = "2023-03-31"

    expected_url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{lang}.wikipedia.org/all-access/user/{slug}/monthly/2023010100/2023033100"
    )

    raw_items = [
        {"project": "pl.wikipedia", "article": slug, "timestamp": "2023010100", "views": 15000},
        {"project": "pl.wikipedia", "article": slug, "timestamp": "2023020100", "views": 17500},
        {"project": "pl.wikipedia", "article": slug, "timestamp": "2023030100", "views": 19000},
    ]

    mock_route = respx.get(expected_url).respond(
        status_code=200,
        json={"items": raw_items},
    )

    async with create_wikimedia_client() as client:
        items = await get_pageviews(
            client=client,
            lang=lang,
            article_slug=slug,
            start_date=start_date,
            end_date=end_date,
            granularity="monthly",
        )

    assert len(items) == 3
    assert items[0].timestamp == "2023010100"
    assert items[0].date == "2023-01"
    assert items[0].views == 15000
    assert mock_route.called
    assert mock_route.calls.last.request.headers.get("user-agent") == USER_AGENT


@pytest.mark.asyncio
@respx.mock
async def test_get_pageviews_404_returns_empty_list():
    """Test 404 response (no data found) returns empty list without error."""
    lang = "es"
    slug = "Ayuno_intermitente"
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{lang}.wikipedia.org/all-access/user/{slug}/monthly/2023010100/2023020100"
    )

    respx.get(url).respond(status_code=404, json={"type": "not_found", "title": "Not found"})

    async with create_wikimedia_client() as client:
        items = await get_pageviews(
            client=client,
            lang=lang,
            article_slug=slug,
            start_date="2023-01-01",
            end_date="2023-02-01",
        )

    assert items == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_all_languages_data_flow():
    """Test full flow: langlinks resolution -> slug formation (spaces to _) -> pageviews extraction."""
    topic = "Intermittent fasting"
    languages = ["pl", "cs"]

    # 1. Mock langlinks API
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

    # 2. Mock PL pageviews API
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/pl.wikipedia.org/all-access/user/Post_przerywany/monthly/2023010100/2023020100"
    ).respond(
        status_code=200,
        json={"items": [{"timestamp": "2023010100", "views": 12000}]},
    )

    # 3. Mock CS pageviews API
    respx.get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/cs.wikipedia.org/all-access/user/Přerušovaný_půst/monthly/2023010100/2023020100"
    ).respond(
        status_code=200,
        json={"items": [{"timestamp": "2023010100", "views": 4500}]},
    )

    async with create_wikimedia_client() as client:
        results = await fetch_all_languages_data(
            client=client,
            base_topic=topic,
            language_codes=languages,
            start_date="2023-01-01",
            end_date="2023-02-01",
            granularity="monthly",
        )

    assert len(results) == 2

    pl_res = next(r for r in results if r.language == "pl")
    assert pl_res.article_title == "Post przerywany"
    assert pl_res.article_slug == "Post_przerywany"
    assert pl_res.found is True
    assert pl_res.total_views == 12000

    cs_res = next(r for r in results if r.language == "cs")
    assert cs_res.article_title == "Přerušovaný půst"
    assert cs_res.article_slug in ["Přerušovaný_půst", "P%C5%99eru%C5%A1ovan%C3%BD_p%C5%AFst"]
    assert cs_res.found is True
    assert cs_res.total_views == 4500


@pytest.mark.asyncio
@respx.mock
async def test_semaphore_limits_concurrency():
    """Verify that semaphore restricts concurrent pageview requests to max_concurrency."""
    import asyncio
    from app.services.wikimedia import MAX_CONCURRENT_REQUESTS

    active_concurrent = 0
    max_observed_concurrent = 0

    # Mock langlinks API with 6 languages
    languages = [f"l{i}" for i in range(6)]
    respx.get("https://en.wikipedia.org/w/api.php").respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "100": {
                        "pageid": 100,
                        "title": "Topic",
                        "langlinks": [{"lang": lang, "*": f"Title_{lang}"} for lang in languages],
                    }
                }
            }
        },
    )

    async def mock_pageviews_callback(request):
        nonlocal active_concurrent, max_observed_concurrent
        active_concurrent += 1
        max_observed_concurrent = max(max_observed_concurrent, active_concurrent)
        await asyncio.sleep(0.02)
        active_concurrent -= 1
        return httpx.Response(200, json={"items": [{"timestamp": "2023010100", "views": 100}]})

    for lang in languages:
        respx.get(
            f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia.org/all-access/user/Title_{lang}/monthly/2023010100/2023020100"
        ).mock(side_effect=mock_pageviews_callback)

    # Test with max_concurrency=2
    async with create_wikimedia_client() as client:
        results = await fetch_all_languages_data(
            client=client,
            base_topic="Topic",
            language_codes=languages,
            start_date="2023-01-01",
            end_date="2023-02-01",
            granularity="monthly",
            max_concurrency=2,
        )

    assert len(results) == 6
    assert max_observed_concurrent <= 2
    assert MAX_CONCURRENT_REQUESTS == 5


@pytest.mark.asyncio
@respx.mock
async def test_resolve_localized_titles_all_languages():
    """Verify resolve_localized_titles with 'all' dynamically resolves all langlinks plus English."""
    respx.get("https://en.wikipedia.org/w/api.php").respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "123": {
                        "pageid": 123,
                        "title": "Coffee",
                        "langlinks": [
                            {"lang": "uk", "*": "Кава"},
                            {"lang": "pl", "*": "Kawa"},
                            {"lang": "de", "*": "Kaffee"},
                        ],
                    }
                }
            }
        },
    )

    async with create_wikimedia_client() as client:
        lang_map = await resolve_localized_titles(client, base_topic="Coffee", language_codes=["all"])

    assert lang_map["en"] == "Coffee"
    assert lang_map["uk"] == "Кава"
    assert lang_map["pl"] == "Kawa"
    assert lang_map["de"] == "Kaffee"
    assert len(lang_map) == 4


def test_align_date_for_pageviews():
    """Verify align_date_for_pageviews handles start, end, and mid-month dates properly."""
    # Monthly start clamps to first of month
    assert align_date_for_pageviews("2023-01-15", is_end=False, granularity="monthly") == "2023010100"
    # Monthly end preserves valid boundary dates
    assert align_date_for_pageviews("2023-01-01", is_end=True, granularity="monthly") == "2023010100"
    assert align_date_for_pageviews("2023-01-31", is_end=True, granularity="monthly") == "2023013100"
    # Monthly end clamps mid-month date to last day of month
    assert align_date_for_pageviews("2023-02-15", is_end=True, granularity="monthly") == "2023022800"
    # Leap year handling
    assert align_date_for_pageviews("2024-02-10", is_end=True, granularity="monthly") == "2024022900"
    # Daily granularity keeps exact date
    assert align_date_for_pageviews("2023-05-15", is_end=False, granularity="daily") == "2023051500"


def test_is_current_period():
    """Verify is_current_period identifies ongoing month/day timestamps."""
    from datetime import datetime
    now = datetime.now()
    current_month_ts = now.strftime("%Y%m0100")
    past_month_ts = "2020010100"

    assert is_current_period(current_month_ts, granularity="monthly") is True
    assert is_current_period(past_month_ts, granularity="monthly") is False


@pytest.mark.asyncio
@respx.mock
async def test_search_article_title_fallback():
    """Verify search fallback extracts title from search hits or suggestion."""
    url = "https://en.wikipedia.org/w/api.php"

    # 1. Search hits
    respx.get(url).respond(
        status_code=200,
        json={"query": {"search": [{"title": "Meat alternative"}]}},
    )
    async with create_wikimedia_client() as client:
        res = await search_article_title_fallback(client, "Plant-based meat")
    assert res == "Meat alternative"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_localized_titles_with_redirect():
    """Verify resolve_localized_titles follows Wikipedia redirects (e.g. AI -> Artificial intelligence)."""
    url = "https://en.wikipedia.org/w/api.php"
    respx.get(url).respond(
        status_code=200,
        json={
            "query": {
                "redirects": [{"from": "AI", "to": "Artificial intelligence"}],
                "pages": {
                    "1164": {
                        "pageid": 1164,
                        "title": "Artificial intelligence",
                        "langlinks": [
                            {"lang": "uk", "*": "Штучний інтелект"},
                            {"lang": "de", "*": "Künstliche Intelligenz"},
                        ],
                    }
                },
            }
        },
    )

    async with create_wikimedia_client() as client:
        lang_map = await resolve_localized_titles(client, base_topic="AI", language_codes=["en", "uk"])

    assert lang_map["en"] == "Artificial intelligence"
    assert lang_map["uk"] == "Штучний інтелект"


@pytest.mark.asyncio
@respx.mock
async def test_resolve_localized_titles_disambiguation_fallback():
    """Verify disambiguation page triggers search fallback to find concrete article."""
    url = "https://en.wikipedia.org/w/api.php"

    disambig_resp = {
        "query": {
            "pages": {
                "100": {
                    "pageid": 100,
                    "title": "Mercury",
                    "pageprops": {"disambiguation": ""},
                }
            }
        }
    }
    search_resp = {
        "query": {
            "search": [{"title": "Mercury (planet)"}],
        }
    }
    concrete_resp = {
        "query": {
            "pages": {
                "200": {
                    "pageid": 200,
                    "title": "Mercury (planet)",
                    "langlinks": [{"lang": "uk", "*": "Меркурій (планета)"}],
                }
            }
        }
    }

    respx.get(url).mock(
        side_effect=[
            httpx.Response(200, json=disambig_resp),
            httpx.Response(200, json=search_resp),
            httpx.Response(200, json=concrete_resp),
        ]
    )

    async with create_wikimedia_client() as client:
        lang_map = await resolve_localized_titles(client, base_topic="Mercury", language_codes=["en", "uk"])

    assert lang_map["en"] == "Mercury (planet)"
    assert lang_map["uk"] == "Меркурій (планета)"


@pytest.mark.asyncio
@respx.mock
async def test_get_pageviews_with_is_partial():
    """Verify PageviewItem marks ongoing periods as is_partial."""
    from datetime import datetime
    now = datetime.now()
    current_ts = now.strftime("%Y%m0100")

    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"en.wikipedia.org/all-access/user/Coffee/monthly/2023010100/2023020100"
    )

    raw_items = [
        {"project": "en.wikipedia", "article": "Coffee", "timestamp": "2023010100", "views": 1000},
        {"project": "en.wikipedia", "article": "Coffee", "timestamp": current_ts, "views": 500},
    ]

    respx.get(url).respond(status_code=200, json={"items": raw_items})

    async with create_wikimedia_client() as client:
        items = await get_pageviews(
            client=client,
            lang="en",
            article_slug="Coffee",
            start_date="2023-01-01",
            end_date="2023-02-01",
            granularity="monthly",
        )

    assert len(items) == 2
    assert items[0].is_partial is False
    assert items[1].is_partial is True


@pytest.mark.asyncio
@respx.mock
async def test_resolve_localized_titles_multilingual_hub():
    """Verify Cyrillic or localized topic resolves via native Wikipedia hub (e.g. uk.wikipedia.org)."""
    uk_url = "https://uk.wikipedia.org/w/api.php"

    respx.get(uk_url).respond(
        status_code=200,
        json={
            "query": {
                "pages": {
                    "555": {
                        "pageid": 555,
                        "title": "Запорозька Січ",
                        "langlinks": [
                            {"lang": "en", "*": "Zaporozhian Sich"},
                            {"lang": "pl", "*": "Sicz Zaporoska"},
                        ],
                    }
                }
            }
        },
    )

    async with create_wikimedia_client() as client:
        lang_map = await resolve_localized_titles(
            client=client,
            base_topic="Запорізька Січ",
            language_codes=["uk", "en", "pl"],
        )

    assert lang_map["uk"] == "Запорозька Січ"
    assert lang_map["en"] == "Zaporozhian Sich"
    assert lang_map["pl"] == "Sicz Zaporoska"



