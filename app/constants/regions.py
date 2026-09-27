"""Geographic regions to Wikipedia language codes mapping and utilities."""

from __future__ import annotations

from typing import Dict, List

REGION_LANGUAGES: Dict[str, List[str]] = {
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

REGION_ALIASES: Dict[str, str] = {
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

    "asia": "asia",
    "азія": "asia",
    "азия": "asia",

    "latin_america": "latin_america",
    "латинська америка": "latin_america",
    "латинская америка": "latin_america",
    "latam": "latin_america",
    "north_america": "north_america",
    "північна америка": "north_america",
    "северная америка": "north_america",

    "middle_east": "middle_east",
    "близький схід": "middle_east",
    "ближний восток": "middle_east",
    "africa": "africa",
    "африка": "africa",

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
    "всі мови",
    "все языки",
}


def expand_region_codes(codes: List[str]) -> List[str]:
    """Expand regional aliases or 'all' into a flat list of Wikipedia language codes."""
    if not codes:
        return ["en"]

    expanded: List[str] = []
    seen = set()

    for raw_code in codes:
        code = raw_code.strip().lower()

        if code in ALL_WORLD_TOKENS or code == "*":
            return ["all"]

        mapped_region = REGION_ALIASES.get(code, code)
        if mapped_region in REGION_LANGUAGES:
            for lang in REGION_LANGUAGES[mapped_region]:
                if lang not in seen:
                    seen.add(lang)
                    expanded.append(lang)
        else:
            if code not in seen:
                seen.add(code)
                expanded.append(code)

    return expanded if expanded else ["en"]
