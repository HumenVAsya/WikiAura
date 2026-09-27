"""Geographic regions to Wikipedia language codes mapping and utilities."""

from __future__ import annotations

from typing import Dict, List

# Standardized regions to ISO 639-1 language codes for Wikipedia editions
REGION_LANGUAGES: Dict[str, List[str]] = {
    # Comprehensive European coverage (25 languages)
    "europe": [
        "en", "de", "fr", "es", "it", "pl", "uk", "nl", "cs", "pt",
        "sv", "ro", "el", "hu", "da", "fi", "sk", "bg", "hr", "sr",
        "no", "lt", "lv", "et", "sl",
    ],
    "eastern_europe": [
        "uk", "pl", "cs", "sk", "ro", "hu", "bg", "hr", "sr", "sl", "en",
    ],
    "western_europe": [
        "en", "de", "fr", "nl", "es", "it", "pt", "de",
    ],
    "scandinavia": [
        "sv", "da", "no", "fi", "is", "en",
    ],
    "nordic": [
        "sv", "da", "no", "fi", "is", "en",
    ],
    "asia": [
        "zh", "ja", "ko", "hi", "id", "vi", "th", "ms", "bn", "ta", "te", "ur", "en",
    ],
    "latin_america": [
        "es", "pt", "en",
    ],
    "latam": [
        "es", "pt", "en",
    ],
    "north_america": [
        "en", "es", "fr",
    ],
    "middle_east": [
        "ar", "fa", "he", "tr", "en",
    ],
    "africa": [
        "ar", "en", "fr", "sw", "am", "ha", "yo", "ig", "pt",
    ],
    "world_major": [
        "en", "zh", "es", "hi", "ar", "bn", "pt", "ru", "ja", "de",
        "fr", "uk", "it", "ko", "tr", "vi", "pl", "nl", "id", "fa",
        "th", "sv", "he", "ro", "cs", "el", "hu", "da", "fi", "no",
    ],
}

# Aliases for flexible matching (Ukrainian, Russian, English)
REGION_ALIASES: Dict[str, str] = {
    # Europe
    "europe": "europe",
    "європа": "europe",
    "европа": "europe",
    "all_europe": "europe",
    "вся європа": "europe",
    "всій європі": "europe",
    "eastern_europe": "eastern_europe",
    "східна європа": "eastern_europe",
    "western_europe": "western_europe",
    "західна європа": "western_europe",
    "scandinavia": "scandinavia",
    "скандинавія": "scandinavia",
    "nordic": "nordic",

    # Asia
    "asia": "asia",
    "азія": "asia",
    "азия": "asia",

    # Americas
    "latin_america": "latin_america",
    "латинська америка": "latin_america",
    "латинская америка": "latin_america",
    "latam": "latin_america",
    "north_america": "north_america",
    "північна америка": "north_america",
    "северная америка": "north_america",

    # Middle East & Africa
    "middle_east": "middle_east",
    "близький схід": "middle_east",
    "ближний восток": "middle_east",
    "africa": "africa",
    "африка": "africa",

    # World / Global
    "world_major": "world_major",
    "top_world": "world_major",
}

ALL_WORLD_TOKENS = {
    "all",
    "world",
    "global",
    "світ",
    "весь світ",
    "по всьому світу",
    "глобально",
    "*",
}


def expand_region_codes(codes_or_regions: List[str]) -> List[str]:
    """Expand list containing region names or codes into a resolved list of language codes.

    If any token requests all/global/world, returns ['all'] to trigger dynamic Wikipedia world resolution.
    """
    if not codes_or_regions:
        return ["en"]

    for item in codes_or_regions:
        normalized = item.strip().lower()
        if normalized in ALL_WORLD_TOKENS:
            return ["all"]

    expanded: List[str] = []
    for item in codes_or_regions:
        key = item.strip().lower().replace("-", "_")
        canonical_region = REGION_ALIASES.get(key, key)
        if canonical_region in REGION_LANGUAGES:
            expanded.extend(REGION_LANGUAGES[canonical_region])
        else:
            expanded.append(item.strip().lower())

    return list(dict.fromkeys(expanded))
