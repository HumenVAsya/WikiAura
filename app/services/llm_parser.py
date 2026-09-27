"""LLM natural language parser service using Google Gemini (via OpenAI-compatible endpoint) and instructor."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import os
from typing import List, Optional
import instructor
import openai

from app.constants.regions import expand_region_codes
from app.schemas.requests import WikipediaQueryParams

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FALLBACK_GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash"]


def build_system_prompt() -> str:
    """Construct LLM system prompt with instructions for concept translation, region mapping, and date handling."""
    today = datetime.now()
    today_str = today.strftime("%Y%m%d")
    one_year_ago_str = (today - timedelta(days=365)).strftime("%Y%m%d")

    return f"""You are a specialized NLP query parser for Wikipedia market and trend analysis.
Current reference date: {today_str}. One year ago: {one_year_ago_str}.

Your goal is to parse natural language queries (in Ukrainian, English, or other languages) into structured `WikipediaQueryParams`:

1. Concept Translation & Native Fallback (`base_topic`, `source_topic`):
   - `base_topic`: Translate abstract, colloquial, or descriptive phrases into the canonical English Wikipedia article title (e.g. 'Coffee', 'Artificial intelligence').
   - `source_topic`: If the query is in Ukrainian or another native language, or refers to a local entity, brand, law, or cultural concept (e.g. 'єПідтримка', 'Дія', 'Запорізька Січ'), keep the original native concept title here as a fallback hub.
   - Use standard Wikipedia title casing (e.g., first word capitalized, proper nouns capitalized).
   - Examples:
     * "статистика по людям які люблять курити" / "куріння" -> base_topic: "Tobacco smoking", source_topic: "Куріння"
     * "статистика по єПідтримці" -> base_topic: "ePidtrymka", source_topic: "єПідтримка"
     * "хто п'є каву" / "кавомани" -> base_topic: "Coffee", source_topic: "Кава"
     * "штучний інтелект" -> base_topic: "Artificial intelligence", source_topic: "Штучний інтелект"
     * "інтервальне голодування" -> base_topic: "Intermittent fasting", source_topic: "Інтервальне голодування"
     * "криптовалюта" / "біткоїн" -> base_topic: "Cryptocurrency", source_topic: "Криптовалюта"
     * "електромобілі" -> base_topic: "Electric car", source_topic: "Електромобіль"

2. Geographic Region & Language Resolution (`language_codes`):
   - Output an array of strings in `language_codes`:
     * Global / Worldwide ("весь світ", "глобально", "all languages", "everywhere", "по всьому світу"):
       Return: ["all"]
     * Regional scope:
       Return the region name or language codes:
       - "Європа" / "Вся Європа" -> ["europe"]
       - "Східна Європа" -> ["eastern_europe"]
       - "Західна Європа" -> ["western_europe"]
       - "Скандинавія" -> ["scandinavia"]
       - "Азія" -> ["asia"]
       - "Латинська Америка" -> ["latin_america"]
       - "Північна Америка" -> ["north_america"]
       - "Близький Схід" -> ["middle_east"]
       - "Африка" -> ["africa"]
       - "Топ світу" -> ["world_major"]
     * Specific country or language (e.g., "в Україні та Польщі" / "німецькою"):
       Return specific ISO 639-1 codes: ["uk", "pl"], ["de"]
     * If no region or language is specified, default to: ["en"]

3. Timeframe & Granularity Resolution (`start_date`, `end_date`, `granularity`):
   - Format: strictly YYYYMMDD (8 digits, e.g., '20230101').
   - If not specified by the user:
     * start_date: 1 year ago ('{one_year_ago_str}')
     * end_date: today ('{today_str}')
   - If a specific year is mentioned (e.g., "у 2023 році"):
     * start_date: '20230101', end_date: '20231231'
   - Granularity: default to 'monthly' unless daily is explicitly requested or date span is under 30 days.
"""


def get_instructor_gemini_client(
    api_key: Optional[str] = None,
    base_url: str = DEFAULT_GEMINI_BASE_URL,
    timeout: float = 20.0,
) -> instructor.AsyncInstructor:
    """Create an instructor-wrapped AsyncOpenAI client pointing to Gemini API."""
    key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please set the GEMINI_API_KEY environment variable."
        )

    openai_client = openai.AsyncOpenAI(
        base_url=base_url,
        api_key=key,
        timeout=timeout,
        max_retries=0,
    )
    return instructor.from_openai(openai_client, mode=instructor.Mode.JSON)


async def parse_user_query_to_schema(
    user_query: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    client: Optional[instructor.AsyncInstructor] = None,
) -> WikipediaQueryParams:
    """Parse natural language query into structured WikipediaQueryParams using Gemini and instructor."""
    target_model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    if client is not None:
        try:
            parsed = await client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_query},
                ],
                response_model=WikipediaQueryParams,
            )
            parsed.language_codes = expand_region_codes(parsed.language_codes)
            return parsed
        except Exception as exc:
            logger.exception("Error parsing user query '%s' with provided client: %s", user_query, exc)
            raise

    gemini_client = get_instructor_gemini_client(api_key=api_key)

    candidate_models: List[str] = [target_model]
    for fb in FALLBACK_GEMINI_MODELS:
        if fb not in candidate_models:
            candidate_models.append(fb)

    last_exc: Optional[Exception] = None
    for current_model in candidate_models:
        try:
            logger.info("Attempting to parse query with model '%s'...", current_model)
            parsed = await gemini_client.chat.completions.create(
                model=current_model,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_query},
                ],
                response_model=WikipediaQueryParams,
            )
            parsed.language_codes = expand_region_codes(parsed.language_codes)
            logger.info("Successfully parsed query with model '%s'", current_model)
            return parsed
        except Exception as exc:
            last_exc = exc
            err_msg = str(exc).lower()
            logger.warning(
                "Model '%s' failed for query '%s' (Error: %s). Checking fallback models...",
                current_model,
                user_query,
                exc,
            )
            if "invalid_api_key" in err_msg or "unauthorized" in err_msg:
                break

    logger.error("All candidate models failed for query '%s': %s", user_query, last_exc)
    raise last_exc  # type: ignore[misc]
