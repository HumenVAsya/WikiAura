from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.schemas.requests import WikipediaQueryParams
from app.services.llm_parser import (
    DEFAULT_GEMINI_MODEL,
    build_system_prompt,
    get_instructor_gemini_client,
    parse_user_query_to_schema,
)


def test_wikipedia_query_params_defaults():
    """Verify default values for WikipediaQueryParams."""
    params = WikipediaQueryParams(base_topic="Tobacco smoking")
    assert params.base_topic == "Tobacco smoking"
    assert params.language_codes == ["en"]
    assert params.granularity == "monthly"
    assert len(params.start_date) == 8
    assert len(params.end_date) == 8
    assert params.start_date.isdigit()
    assert params.end_date.isdigit()


def test_build_system_prompt():
    """Verify system prompt contains instructions for concept translation and regions."""
    prompt = build_system_prompt()
    assert "Tobacco smoking" in prompt
    assert "language_codes" in prompt
    assert "Європа" in prompt
    assert "YYYYMMDD" in prompt


@pytest.mark.asyncio
async def test_parse_user_query_to_schema_with_mocked_client():
    """Verify parse_user_query_to_schema invokes instructor chat.completions.create with gemini-3.5-flash."""
    mock_instructor_client = MagicMock()
    mock_chat = MagicMock()
    mock_completions = MagicMock()
    mock_instructor_client.chat = mock_chat
    mock_chat.completions = mock_completions

    expected_params = WikipediaQueryParams(
        base_topic="Tobacco smoking",
        language_codes=["en", "de", "fr", "pl", "uk"],
        start_date="20250101",
        end_date="20260101",
        granularity="monthly",
    )
    mock_completions.create = AsyncMock(return_value=expected_params)

    query = "статистика по всій європі по людям які люблять курити"
    result = await parse_user_query_to_schema(query, client=mock_instructor_client)

    assert result == expected_params
    assert result.base_topic == "Tobacco smoking"
    assert result.language_codes == ["en", "de", "fr", "pl", "uk"]

    mock_completions.create.assert_awaited_once()
    call_kwargs = mock_completions.create.call_args.kwargs
    assert call_kwargs["model"] == DEFAULT_GEMINI_MODEL
    assert call_kwargs["response_model"] == WikipediaQueryParams
    assert call_kwargs["messages"][1] == {"role": "user", "content": query}


@pytest.mark.asyncio
async def test_parse_user_query_to_schema_missing_api_key():
    """Verify missing API key raises ValueError."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
            await parse_user_query_to_schema("test query", api_key=None, client=None)


def test_get_instructor_gemini_client():
    """Verify client initialization with API key."""
    client = get_instructor_gemini_client(api_key="test-gemini-key")
    assert client is not None


def test_expand_region_codes():
    """Verify expand_region_codes handles regions, global tokens, and specific codes."""
    from app.constants.regions import expand_region_codes

    # Global / all
    assert expand_region_codes(["all"]) == ["all"]
    assert expand_region_codes(["весь світ"]) == ["all"]
    assert expand_region_codes(["world"]) == ["all"]

    # Europe region expansion
    europe_langs = expand_region_codes(["europe"])
    assert "uk" in europe_langs
    assert "de" in europe_langs
    assert "pl" in europe_langs
    assert "en" in europe_langs
    assert len(europe_langs) >= 20

    # Specific country language codes preserved
    assert expand_region_codes(["uk", "pl"]) == ["uk", "pl"]

    # Default fallback
    assert expand_region_codes([]) == ["en"]

