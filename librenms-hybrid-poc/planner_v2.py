#!/usr/bin/env python3
"""Deterministic-first planning helpers for catalog/device-set queries.

This module owns lightweight user-language extraction. Resolver v5 receives only
structured constraints plus an optional explicit catalog reference.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any, Dict, List, Optional

DEVICE_FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": ["string", "null"]},
        "family": {"type": ["string", "null"]},
        "port_count": {"type": ["integer", "null"], "minimum": 1},
        "poe": {"type": ["boolean", "null"]},
    },
    "required": ["brand", "family", "port_count", "poe"],
}

EMPTY_FILTERS = {"brand": None, "family": None, "port_count": None, "poe": None}

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
# "48 port", "48 portlu", "48-port": explicit port-count phrase. The trailing
# \w* keeps ordinary Turkish suffixes from hiding the facet.
_PORT_COUNT_RE = re.compile(r"(?<!\w)(\d{1,3})\s*[- ]?\s*ports?\w*", re.I)
# Catalog shorthand "48G"/"24G"/"8G": <port count> at <link speed>. The speed
# itself has no field in the current filter schema, so only the count is taken.
_PORT_SPEED_RE = re.compile(r"(?<!\w)(\d{1,3})\s*G(?!\w)", re.I)
# A device-set request is signalled by a COLLECTION noun, not by a retrieval
# verb. "göster"/"getir"/"listele" only say that something should be returned;
# they say nothing about whether the subject is a set of devices or one
# device's ports. Treating them as set cues is what made
# "J9774A portlarını göster" look like a device-set request.
_SET_CUES = {
    "hangileri", "olanlar", "olanları", "olanlari",
    "switchler", "switchleri", "switchlerini",
    "cihazlar", "cihazları", "cihazlari", "cihazlarını", "cihazlarini",
    "modeller", "modelleri", "modellerini",
}
_POE_FALSE_RE = re.compile(r"\b(?:poe\s*(?:olmayan|degil|değil)|poesiz)\b", re.I)
_POE_TRUE_RE = re.compile(r"\b(?:poe(?:['’]?li)?|poeli)\b", re.I)


def _words(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text or "")]


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9çğıöşü]+", "", str(value or "").lower())


def _has_set_cue(query: str) -> bool:
    words = set(_words(query))
    return bool(words & _SET_CUES)


def _extract_port_count(query: str) -> Optional[int]:
    m = _PORT_COUNT_RE.search(query or "")
    if m:
        return int(m.group(1))
    m = _PORT_SPEED_RE.search(query or "")
    return int(m.group(1)) if m else None


def _extract_poe(query: str) -> Optional[bool]:
    if _POE_FALSE_RE.search(query or ""):
        return False
    if _POE_TRUE_RE.search(query or ""):
        return True
    return None


def _family_in_query(query: str, families: List[str]) -> Optional[str]:
    words = _words(query)
    for family in sorted(families, key=lambda x: -len(str(x))):
        f = _compact(family)
        if not f:
            continue
        for word in words:
            w = _compact(word)
            if w == f:
                return family
            # Numeric/model families commonly take Turkish plural/case suffixes.
            if any(ch.isdigit() for ch in f) and w.startswith(f) and len(w) - len(f) <= 6:
                return family
    return None


def _literal_occurrence(needle: str, haystack: str) -> bool:
    """Substring match on token boundaries, with separators preserved."""
    start = 0
    while True:
        i = haystack.find(needle, start)
        if i < 0:
            return False
        before = haystack[i - 1] if i > 0 else ""
        end = i + len(needle)
        after = haystack[end] if end < len(haystack) else ""
        if not before.isalnum() and not after.isalnum():
            return True
        start = i + 1


def _catalog_reference(query: str, context: Dict[str, Any]) -> Optional[str]:
    """Return an explicit catalog identity only when the user wrote one.

    A SKU is a single token, so it is matched on the compacted form. A model
    name carries its own separator structure, and that structure is exactly
    what separates an exact model identity from a facet phrase: "2530 48G"
    means family 2530 with 48 ports and must keep matching both the PoE and the
    non-PoE model, while "2530-48G" names one model. Compacting the query
    erased that difference and silently narrowed the set.
    """
    if not str(query or "").strip():
        return None
    compact_q = _compact(query)
    lowered = " ".join(str(query).lower().split())

    refs: List[Any] = []
    for raw in context.get("skus", []) or []:
        norm = _compact(raw)
        if norm and norm in compact_q:
            refs.append((len(norm), raw))
    for raw in context.get("models", []) or []:
        literal = " ".join(str(raw).lower().split())
        if literal and _literal_occurrence(literal, lowered):
            refs.append((len(literal), raw))

    if not refs:
        return None
    refs.sort(reverse=True, key=lambda x: x[0])
    return refs[0][1]


def _brand_from_query(query: str, brands: List[str]) -> Optional[str]:
    words = _words(query)
    # Catalog-derived brand tokens. No product-specific query string is encoded.
    for brand in brands:
        brand_words = [w for w in _words(brand) if len(w) >= 2]
        for bw in brand_words:
            for qw in words:
                # hp/hpe are treated as the same vendor stem, while longer terms
                # use conservative fuzzy matching for realistic spelling errors.
                if {bw, qw} <= {"hp", "hpe"}:
                    return brand
                if qw.startswith(bw) or bw.startswith(qw):
                    if min(len(qw), len(bw)) >= 3:
                        return brand
                if min(len(qw), len(bw)) >= 5:
                    # Compare the catalog-token-length stem too, so ordinary
                    # Turkish suffixes do not hide a spelling-near brand token.
                    stem = qw[:len(bw)] if len(qw) >= len(bw) else qw
                    if max(
                        SequenceMatcher(None, qw, bw).ratio(),
                        SequenceMatcher(None, stem, bw).ratio(),
                    ) >= 0.85:
                        return brand
    return None


def try_deterministic_device_set_plan(query: str, resolver_module, inventory) -> Optional[Dict[str, Any]]:
    """Return a complete device_set plan only when deterministic ownership is clear.

    Other intents intentionally fall through to the Qwen planner.
    """
    if not _has_set_cue(query):
        return None
    if not hasattr(resolver_module, "planner_catalog_context"):
        return None

    context = resolver_module.planner_catalog_context(inventory)
    filters = dict(EMPTY_FILTERS)
    filters["brand"] = _brand_from_query(query, context.get("brands", []))
    filters["family"] = _family_in_query(query, context.get("families", []))
    filters["port_count"] = _extract_port_count(query)
    filters["poe"] = _extract_poe(query)
    reference = _catalog_reference(query, context)

    if reference is None and not any(v is not None for v in filters.values()):
        return None

    return {
        "request_type": "device_set",
        "intent": "device_set",
        "device_query": reference,
        "device_filters": filters,
    }


def normalize_plan_filters(plan: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(plan)
    filters = dict(EMPTY_FILTERS)
    supplied = out.get("device_filters")
    if isinstance(supplied, dict):
        for key in filters:
            if key in supplied:
                filters[key] = supplied[key]
    out["device_filters"] = filters
    return out
