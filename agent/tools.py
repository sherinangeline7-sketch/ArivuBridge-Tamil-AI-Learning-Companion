"""Guidance lookup and language detection tools for ArivuBridge.

lookup_guidance searches by:
  1. Subject name (e.g. "dbms", "python", "os")
  2. Topic keywords in the item's topic field
  3. Full text of the item (English and Tamil both stored there)
  4. Tamil→English keyword map for common bilingual terms

Scoring: every matching word adds 1 point. Items are returned in
descending score order, up to MAX_RESULTS. Items with zero matches
are never returned (no unrelated fallback dump).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from strands import tool

DATA = Path(__file__).parent / "data"

# Matches Tamil Unicode block (U+0B80–U+0BFF) AND standard word chars.
# This lets re.findall tokenise Tamil words correctly.
_WORD_RE = re.compile(r"[\u0B80-\u0BFF]+|[a-zA-Z0-9]+")

# Minimum word length to be treated as a keyword (avoids noise from
# single letters, short prepositions, etc.)
_MIN_LEN = 2

# Maximum items returned by lookup_guidance
MAX_RESULTS = 6

# ---------------------------------------------------------------------------
# Tamil → English keyword map
# Keys are Tamil words that appear in guidance.json "text" fields.
# Values are English keywords used in the same items' id/topic/text.
# Only terms actually present in the guidance content are listed here.
# ---------------------------------------------------------------------------
TAMIL_TO_ENGLISH: dict[str, list[str]] = {
    # DBMS
    "தரவுத்தள":        ["database", "dbms"],
    "தரவுத்தளம்":      ["database", "dbms"],
    "தரவுகளை":         ["database", "dbms", "data"],
    "நார்மலைசேஷன்":    ["normalisation", "normalization", "1nf", "2nf", "3nf"],
    "அட்டவணை":         ["table", "sql", "dbms"],
    "நெடுவரிசை":       ["column", "sql"],
    "வரிசை":           ["row", "sql"],
    "transaction":     ["transaction", "acid", "commit", "rollback"],
    # OS / memory
    "நினைவக":          ["memory", "paging", "virtual"],
    "நினைவகத்தை":      ["memory", "paging", "segmentation"],
    "நிர்வாகம்":       ["management", "memory", "os"],
    "நிர்வகிக்கிறது":  ["management", "os"],
    "செயல்முறை":       ["process", "os"],
    "இயக்க":           ["operating", "os"],
    # Python
    "பட்டியல்":        ["list", "python"],
    "சுழற்சி":         ["loop", "python"],
    "வகைகள்":          ["types", "python"],
    "கோப்பு":          ["file", "python"],
    "பிழை":            ["exception", "error", "python"],
    "வரையறுக்கப்படும்": ["function", "def", "python"],
    # Java
    "வார்ப்புரு":      ["class", "java"],
    "நிகழ்வு":         ["object", "instance", "java"],
    "ஒப்பந்தம்":       ["interface", "java"],
    "பண்புகளை":        ["inheritance", "java"],
    # DSA
    "வரிசைப்படுத்துதல்": ["sorting", "dsa"],
    "கட்டமைப்பு":      ["structure", "data", "dsa"],
    "சங்கிலி":         ["linked", "list", "node"],
    "படிநிலை":         ["tree", "hierarchy"],
    # CN
    "நெட்வொர்க்":      ["network", "cn"],
    "இணைக்கிறது":      ["connect", "network", "router"],
    "தொடர்பு":         ["communication", "network", "cn"],
    "குறியாக்கம்":     ["encryption", "https", "security"],
    # AI
    "இயந்திரங்களில்":  ["machine", "ai", "artificial"],
    "கற்கும்":         ["learning", "machine", "ml"],
    "தேடல்":           ["search", "algorithm", "bfs", "dfs"],
    "முன்மொழி":        ["propositional", "logic", "knowledge"],
}


@lru_cache(maxsize=1)
def guidance() -> dict:
    """Load guidance.json once and cache it."""
    return json.loads((DATA / "guidance.json").read_text(encoding="utf-8"))


def guidance_ids() -> set[str]:
    """Return the set of all valid guidance item IDs."""
    return {g["id"] for g in guidance()["items"]}


def language_of(text: str) -> str:
    """Return 'ta' if the text contains Tamil script characters, else 'en'."""
    return "ta" if _TAMIL_RE.search(text or "") else "en"


def has_tamil(text: str) -> bool:
    """Return True if the text contains any Tamil script characters."""
    return bool(_TAMIL_RE.search(text or ""))


# Keep the original Tamil detector as a module-level compiled pattern.
_TAMIL_RE = re.compile(r"[\u0B80-\u0BFF]")


def _extract_keywords(query: str) -> list[str]:
    """Tokenise a query into lowercase keywords of length >= _MIN_LEN.

    Works for English, Tamil, and mixed input.
    Tamil Unicode words and ASCII words are both matched.
    """
    raw = _WORD_RE.findall(query)
    keywords = [w.lower() for w in raw if len(w) >= _MIN_LEN]

    # Expand Tamil keywords to their English equivalents so they hit
    # the English content in guidance items.
    expanded: list[str] = []
    for kw in keywords:
        expanded.append(kw)
        if kw in TAMIL_TO_ENGLISH:
            expanded.extend(TAMIL_TO_ENGLISH[kw])

    return list(dict.fromkeys(expanded))  # deduplicate while preserving order


def _score_item(item: dict, keywords: list[str]) -> int:
    """Return the number of keywords that appear in this item's searchable text.

    Searchable fields: id, subject, topic, text (all lowercased).
    Each keyword contributes at most 1 point regardless of how many
    times it appears in the combined text.
    """
    haystack = " ".join([
        item.get("id", ""),
        item.get("subject", ""),
        item.get("topic", ""),
        item.get("text", ""),
    ]).lower()

    return sum(1 for kw in keywords if kw in haystack)


@tool
def lookup_guidance(topic: str) -> list[dict]:
    """Find curated, dated CS guidance items to cite. Returns items with id and text.

    Searches guidance IDs, subject names, topic keywords, and the full
    explanation text (English and Tamil). Tamil keywords are automatically
    expanded to their English equivalents before searching.

    Returns up to 6 relevant items ranked by relevance score.
    Returns an empty list with a message item when nothing is relevant.

    Args:
        topic: keywords describing the concept to look up (English or Tamil)
    """
    keywords = _extract_keywords(topic)

    if not keywords:
        return [{"id": "NO-MATCH", "text": "No keywords found in query. Please describe the concept you want to learn about."}]

    items = guidance()["items"]

    # Score every item
    scored = [(item, _score_item(item, keywords)) for item in items]

    # Keep only items with at least one keyword match
    matches = [(item, score) for item, score in scored if score > 0]

    if not matches:
        return [{"id": "NO-MATCH",
                 "text": f"No guidance found for '{topic}'. Try keywords like: sql, python, java, sorting, memory, network, AI, or their Tamil equivalents."}]

    # Sort by score descending, then by id for determinism
    matches.sort(key=lambda x: (-x[1], x[0]["id"]))

    return [{"id": item["id"], "text": item["text"]} for item, _ in matches[:MAX_RESULTS]]
