#!/usr/bin/env python3
"""Runtime catalog ingest and identity index for the natural-language layer.

This module parses controlled catalog model strings, not user language.
Unknown facets stay None. Ingest never silently drops an unparsed row.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

_ALNUM_RE = re.compile(r"[^A-Z0-9]+")
_PORT_RE = re.compile(r"-(\d+)(G|FE)?(?:-|$)", re.I)
_UPLINK_RE = re.compile(r"(?:^|-)(\d+)(SFP\+|SFP)(?:-|$)", re.I)
_SKU_RE = re.compile(r"^(?P<prefix>[A-Z]+)?(?P<number>\d+)(?P<suffix>[A-Z]+)?$")


def normalize_identity(value: Any) -> str:
    if value is None:
        return ""
    return _ALNUM_RE.sub("", str(value).upper())


def _family_from_model(model: str) -> Optional[str]:
    model = (model or "").strip()
    if not model:
        return None
    return model.split("-", 1)[0] or None


def _poe_from_model(model: str, port_count: Optional[int]) -> Tuple[Optional[bool], Optional[str]]:
    upper = (model or "").upper()
    if "POE+" in upper:
        return True, "poe_plus"
    if "POEP" in upper:
        return True, "poep"
    if re.search(r"(?:^|-)POE(?:-|$)", upper):
        return True, "poe"
    # For a fixed-port model whose product string contains a parsed port count,
    # absence of a PoE marker is meaningful. Chassis/opaque names remain unknown.
    if port_count is not None:
        return False, "none"
    return None, None


def _uplinks_from_model(model: str) -> Optional[Dict[str, int]]:
    out: Dict[str, int] = {}
    for count, kind in _UPLINK_RE.findall(model or ""):
        key = "sfp_plus" if kind.upper() == "SFP+" else "sfp"
        out[key] = out.get(key, 0) + int(count)
    return out or None


def parse_catalog_model(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Return normalized facets for one catalog model entry.

    The source may already split sku/model, as the current inventory does. If it
    does not, canonical_name is used conservatively as a fallback.
    """
    sku = str(entry.get("sku") or "").strip() or None
    model = str(entry.get("model") or "").strip() or None

    if (not sku or not model) and entry.get("canonical_name"):
        raw = str(entry["canonical_name"]).strip()
        parts = raw.split(None, 1)
        if not sku and parts:
            sku = parts[0]
        if not model and len(parts) > 1:
            model = parts[1]

    family = _family_from_model(model or "")
    port_count: Optional[int] = None
    speed: Optional[str] = None
    if model:
        m = _PORT_RE.search(model)
        if m:
            port_count = int(m.group(1))
            speed = "1G" if (m.group(2) or "").upper() == "G" else None

    poe, poe_level = _poe_from_model(model or "", port_count)
    uplinks = _uplinks_from_model(model or "")

    missing = []
    if not sku:
        missing.append("sku")
    if not model:
        missing.append("model")
    if family is None:
        missing.append("family")
    if port_count is None:
        missing.append("port_count")
    if poe is None:
        missing.append("poe")

    # A row is failed only when identity itself cannot be recovered. Facet gaps
    # are partial and must remain visible to downstream filtering.
    if not sku and not model:
        parse_status = "failed"
    elif missing:
        parse_status = "partial"
    else:
        parse_status = "complete"

    return {
        "sku": sku,
        "family": family,
        "model": model,
        "port_count": port_count,
        "speed": speed,
        "poe": poe,
        "poe_level": poe_level,
        "uplinks": uplinks,
        "parse_status": parse_status,
        "unknown_fields": missing,
    }


def _add_variant(out: Dict[str, Dict[str, Any]], raw: Optional[str], weight: float, kind: str) -> None:
    norm = normalize_identity(raw)
    if not norm:
        return
    previous = out.get(norm)
    item = {"variant": norm, "weight": float(weight), "variant_type": kind}
    if previous is None or item["weight"] > previous["weight"]:
        out[norm] = item


def identity_variants(entry: Dict[str, Any], facets: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Generate catalog-driven identity variants with explicit confidence.

    No product literal is embedded here. The same rules apply to every SKU.
    """
    facets = facets or parse_catalog_model(entry)
    out: Dict[str, Dict[str, Any]] = {}
    sku = normalize_identity(facets.get("sku"))
    model = str(facets.get("model") or "")
    family = str(facets.get("family") or "")

    _add_variant(out, sku, 1.00, "sku_exact")
    if sku:
        m = _SKU_RE.match(sku)
        if m:
            prefix = m.group("prefix") or ""
            number = m.group("number") or ""
            suffix = m.group("suffix") or ""
            if prefix:
                _add_variant(out, prefix[1:] + number + suffix, 0.90, "sku_missing_first_prefix_char")
                _add_variant(out, number + suffix, 0.90, "sku_missing_prefix")
            if suffix:
                _add_variant(out, prefix + number + suffix[:-1], 0.85, "sku_missing_last_suffix_char")
                _add_variant(out, prefix + number, 0.85, "sku_missing_suffix")
            _add_variant(out, number, 0.70, "sku_numeric_core")

    _add_variant(out, model, 1.00, "model_exact")
    if model:
        # Dropping feature suffixes yields a broad model-family variant such as
        # 2530-48G. Collisions are intentional and are handled as ambiguity.
        pieces = model.split("-")
        if len(pieces) >= 2:
            _add_variant(out, "-".join(pieces[:2]), 0.82, "model_base")
    _add_variant(out, family, 0.72, "family")

    return sorted(out.values(), key=lambda x: (-x["weight"], x["variant"]))


def ingest_models(models: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    enriched: List[Dict[str, Any]] = []
    report = {"complete": 0, "partial": 0, "failed": 0, "flagged": []}
    variant_index: Dict[str, List[Dict[str, Any]]] = {}

    for position, original in enumerate(models):
        model = dict(original)
        facets = parse_catalog_model(model)
        variants = identity_variants(model, facets)
        model["facets"] = facets
        model["identity_variants"] = variants
        enriched.append(model)

        status = facets["parse_status"]
        report[status] += 1
        if status != "complete":
            report["flagged"].append({
                "index": position,
                "sku": facets.get("sku"),
                "model": facets.get("model"),
                "status": status,
                "unknown_fields": list(facets.get("unknown_fields") or []),
            })

        for variant in variants:
            variant_index.setdefault(variant["variant"], []).append({
                "model_index": position,
                "sku": facets.get("sku"),
                "model": facets.get("model"),
                "weight": variant["weight"],
                "variant_type": variant["variant_type"],
            })

    families = sorted({m["facets"]["family"] for m in enriched if m["facets"].get("family")})
    brands = sorted({str(m.get("brand")).strip() for m in enriched if m.get("brand")})
    return {
        "models": enriched,
        "variant_index": variant_index,
        "families": families,
        "brands": brands,
        "report": report,
    }
