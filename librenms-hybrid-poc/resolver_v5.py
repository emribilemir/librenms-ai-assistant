#!/usr/bin/env python3
"""Runtime resolver v5: structured catalog filtering + catalog identity variants.

Frozen resolver_candidate_v4.py remains untouched and is used only as a
compatibility engine for established hostname/alias/exact-metadata behavior.
Natural-language facet extraction does not live in this resolver.
"""
from __future__ import annotations

import importlib.util
import os
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_sibling(name: str, filename: str):
    path = os.path.join(HERE, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_v4 = _load_sibling("resolver_runtime_compat", "resolver.py")
_ingest = _load_sibling("catalog_ingest_v5", "catalog_ingest.py")

# Re-export stable formatter/status API expected by the existing harness.
load_inventory = _v4.load_inventory
lookup_status = _v4.lookup_status
format_atomic = _v4.format_atomic
format_clarification = _v4.format_clarification
normalize = _v4.normalize

_FUZZY_THRESHOLD = 0.85
_AUTO_RESOLVE_SCORE = 0.60
_AMBIGUITY_RATIO = 0.90
_INDEX_CACHE: Dict[int, Tuple[Dict[str, Any], Dict[str, Any]]] = {}


def _dedupe_devices(devices: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for d in devices:
        did = d.get("device_id")
        key = ("id", str(did)) if did is not None else ("hostname", _ingest.normalize_identity(d.get("hostname")))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _device_map_by_sku(devices: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for d in devices:
        out.setdefault(_ingest.normalize_identity(d.get("sku")), []).append(d)
    return out


def build_index(inventory: Dict[str, Any]) -> Dict[str, Any]:
    catalog = _ingest.ingest_models(inventory.get("models", []))
    devices = list(inventory.get("devices", []))
    return {
        **catalog,
        "devices": devices,
        "devices_by_sku": _device_map_by_sku(devices),
    }


def get_index(inventory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if inventory is None:
        inventory = load_inventory()
    key = id(inventory)
    cached = _INDEX_CACHE.get(key)
    if cached is not None and cached[0] is inventory:
        return cached[1]
    idx = build_index(inventory)
    _INDEX_CACHE[key] = (inventory, idx)
    return idx


def clear_index_cache() -> None:
    _INDEX_CACHE.clear()


def planner_catalog_context(inventory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    idx = get_index(inventory)
    models = idx["models"]
    return {
        "brands": list(idx["brands"]),
        "families": list(idx["families"]),
        "skus": [m["facets"].get("sku") for m in models if m["facets"].get("sku")],
        "models": [m["facets"].get("model") for m in models if m["facets"].get("model")],
        "ingest_report": idx["report"],
    }


def catalog_ingest_report(inventory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return get_index(inventory)["report"]


def _models_to_devices(models: Iterable[Dict[str, Any]], idx: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for model in models:
        sku = _ingest.normalize_identity(model.get("facets", {}).get("sku") or model.get("sku"))
        out.extend(idx["devices_by_sku"].get(sku, []))
    return _dedupe_devices(out)


def _variant_candidates(reference: Any, idx: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = _ingest.normalize_identity(reference)
    if not q:
        return []

    hits = idx["variant_index"].get(q)
    if hits:
        return sorted((dict(h, score=float(h["weight"]), similarity=1.0) for h in hits), key=lambda x: -x["score"])

    # Fuzzy is a fallback only. It runs against finite catalog variants, never
    # the raw language corpus, and has no SKU-specific literals.
    candidates: Dict[int, Dict[str, Any]] = {}
    for variant, entries in idx["variant_index"].items():
        similarity = SequenceMatcher(None, q, variant).ratio()
        if similarity < _FUZZY_THRESHOLD:
            continue
        for entry in entries:
            score = similarity * float(entry["weight"])
            current = candidates.get(entry["model_index"])
            candidate = dict(entry, score=score, similarity=similarity, matched_variant=variant)
            if current is None or score > current["score"]:
                candidates[entry["model_index"]] = candidate
    return sorted(candidates.values(), key=lambda x: -x["score"])


def _variant_resolution(reference: Any, inventory: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    idx = get_index(inventory)
    candidates = _variant_candidates(reference, idx)
    if not candidates:
        return None

    best_score = candidates[0]["score"]
    if best_score < _AUTO_RESOLVE_SCORE:
        devices = _models_to_devices([idx["models"][c["model_index"]] for c in candidates[:5]], idx)
        return {
            "outcome": "ambiguous",
            "reason": "ambiguous",
            "device": None,
            "candidates": devices,
            "candidate_details": candidates[:5],
        }

    competitive = [c for c in candidates if c["score"] / best_score > _AMBIGUITY_RATIO]
    models = [idx["models"][c["model_index"]] for c in competitive]
    devices = _models_to_devices(models, idx)

    # Even one catalog model can represent multiple device instances. A single-
    # device query must never pick one of those instances arbitrarily.
    if len(competitive) > 1 or len(devices) != 1:
        return {
            "outcome": "ambiguous",
            "reason": "ambiguous",
            "device": None,
            "candidates": devices,
            "candidate_details": competitive,
            "models": models,
        }

    return {
        "outcome": "resolved",
        "reason": "metadata",
        "device": devices[0],
        "candidates": [],
        "query": str(reference),
        "models": models,
        "match": {
            "variant_type": competitive[0]["variant_type"],
            "score": round(competitive[0]["score"], 4),
            "similarity": round(competitive[0]["similarity"], 4),
        },
    }


def resolve_device(query: Any, inventory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if inventory is None:
        inventory = load_inventory()

    # Preserve the frozen, already-tested hostname/alias/exact metadata path.
    result = _v4.resolve_device(query, inventory)
    if result.get("outcome") != "no_match":
        return result

    # Add only the missing generic catalog-reference capability.
    variant = _variant_resolution(query, inventory)
    return variant if variant is not None else result


def _norm_text(value: Any) -> str:
    return _ingest.normalize_identity(value)


def _brand_matches(requested: str, catalog_brand: str) -> bool:
    q = _norm_text(requested)
    b = _norm_text(catalog_brand)
    return bool(q and b and (q == b or q in b or b in q))


def _reference_models(reference: Any, idx: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    if reference is None or not str(reference).strip():
        return None

    # Exact finite-catalog identity variants first.
    candidates = _variant_candidates(reference, idx)
    if candidates:
        top = candidates[0]["score"]
        competitive = [c for c in candidates if c["score"] / top > _AMBIGUITY_RATIO]
        return [idx["models"][c["model_index"]] for c in competitive]

    # Compatibility for explicit broad catalog references such as "2530 48G".
    # This reuses v4 metadata matching only for a planner-provided reference,
    # never for feature-only raw natural language.
    base = _v4.resolve_device_set(reference, {"models": [
        {k: v for k, v in m.items() if k not in ("facets", "identity_variants")}
        for m in idx["models"]
    ], "devices": idx["devices"]})
    if base.get("outcome") == "resolved":
        wanted = {_norm_text(m.get("sku")) for m in base.get("models", [])}
        return [m for m in idx["models"] if _norm_text(m.get("facets", {}).get("sku")) in wanted]
    return []


def _filter_model(model: Dict[str, Any], filters: Dict[str, Any]) -> Tuple[bool, List[str]]:
    facets = model["facets"]
    unknown: List[str] = []

    brand = filters.get("brand")
    if brand is not None and not _brand_matches(str(brand), str(model.get("brand") or "")):
        return False, unknown

    family = filters.get("family")
    if family is not None:
        actual = facets.get("family")
        if actual is None:
            unknown.append("family")
        elif _norm_text(actual) != _norm_text(family):
            return False, unknown

    port_count = filters.get("port_count")
    if port_count is not None:
        actual = facets.get("port_count")
        if actual is None:
            unknown.append("port_count")
        elif int(actual) != int(port_count):
            return False, unknown

    poe = filters.get("poe")
    if poe is not None:
        actual = facets.get("poe")
        if actual is None:
            unknown.append("poe")
        elif bool(actual) is not bool(poe):
            return False, unknown

    return len(unknown) == 0, unknown


def resolve_device_set(query: Any = None, inventory: Optional[Dict[str, Any]] = None,
                       filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply planner-owned structured constraints to the finite catalog.

    query is an optional explicit catalog identity/reference. It is not parsed as
    natural-language facets. filters owns brand/family/port_count/poe semantics.
    """
    if inventory is None:
        inventory = load_inventory()
    idx = get_index(inventory)
    filters = dict(filters or {})
    for key in ("brand", "family", "port_count", "poe"):
        filters.setdefault(key, None)

    has_filters = any(filters.get(k) is not None for k in ("brand", "family", "port_count", "poe"))
    reference_models = _reference_models(query, idx)

    if reference_models is None:
        candidates = list(idx["models"])
    else:
        candidates = list(reference_models)

    matched: List[Dict[str, Any]] = []
    unevaluated: List[Dict[str, Any]] = []
    unevaluated_fields = set()

    for model in candidates:
        if not has_filters:
            matched.append(model)
            continue
        ok, unknown = _filter_model(model, filters)
        if unknown:
            unevaluated.append(model)
            unevaluated_fields.update(unknown)
        elif ok:
            matched.append(model)

    devices = _models_to_devices(matched, idx)
    unevaluated_devices = _models_to_devices(unevaluated, idx)

    if not matched and not unevaluated:
        return {
            "outcome": "no_match",
            "reason": "no_match",
            "models": [],
            "devices": [],
            "filters": filters,
            "unevaluated_models": [],
            "unevaluated_devices": [],
            "unevaluated_count": 0,
            "unevaluated_fields": [],
        }

    # Matching and uncertainty are separate. A result can be resolved while also
    # reporting catalog rows that could not be evaluated for the requested facet.
    return {
        "outcome": "resolved" if (matched or unevaluated) else "no_match",
        "reason": "metadata" if matched else "indeterminate_catalog",
        "models": matched,
        "devices": devices,
        "filters": filters,
        "matched_fields": [k for k in ("brand", "family", "port_count", "poe") if filters.get(k) is not None]
                          + (["reference"] if query is not None else []),
        "unevaluated_models": unevaluated,
        "unevaluated_devices": unevaluated_devices,
        "unevaluated_count": len(unevaluated_devices),
        "unevaluated_model_count": len(unevaluated),
        "unevaluated_fields": sorted(unevaluated_fields),
        "ingest_report": idx["report"],
    }


def format_device_set(result: Dict[str, Any]) -> str:
    count = int(result.get("unevaluated_count") or 0)
    fields = result.get("unevaluated_fields") or []
    models = result.get("models") or []
    devices = result.get("devices") or []
    if not models and not devices and count:
        text = "Kesin eşleşme belirlenemedi."
    else:
        parts = []
        if models:
            names = ", ".join(
                model.get("canonical_name", model.get("sku", ""))
                for model in models
            )
            parts.append("Model(ler): " + names)
        if devices:
            hostnames = ", ".join(device["hostname"] for device in devices)
            parts.append("Cihazlar: " + hostnames)
        text = " ".join(parts) + "." if parts else "Eşleşen model/cihaz bulunamadı."
    if count:
        human = ", ".join(fields) if fields else "istenen özellik"
        text += f" {count} cihaz {human} bilgisi katalogda bilinmediği için değerlendirilemedi."
    return text
