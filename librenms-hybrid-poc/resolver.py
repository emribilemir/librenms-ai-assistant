#!/usr/bin/env python3
"""
Deterministic entity resolver for the LibreNMS hybrid PoC (v2).

Pure Python, no LLM, no network. Resolves device references against an
inventory of devices plus a model catalog, and returns structured outcomes
with an explicit reason from the closed set:

    exact | normalized | alias | typo | metadata | ambiguous | no_match

Layers (single-device resolve_device), highest confidence first:
    1. exact hostname      (case-insensitive literal equality)
    2. normalized hostname (case/space/hyphen/underscore/clitic insensitive)
    3. alias               (device-level alias, or catalog model alias)
    4. typo                (edit distance <= 1 + keyboard/prefix/suffix scoring)
    5. metadata            (brand/sku/model/canonical_name/search_text)
    6. ambiguous / no_match

resolve_device_set() is a separate FILTER path for model/group references: it
returns every matching model/device rather than picking one.
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_EDIT_DISTANCE = 1
AUTO_RESOLVE_MARGIN = 25
TYPO_CONFIDENCE_THRESHOLD = 70
PREFIX_SCORE = 20

# Generic device-type words that carry no discriminating information about a
# specific hostname. "sw" is deliberately NOT here (real prefix of the sw-* family).
GENERIC_TYPE_TOKENS = {
    "switch", "switches", "device", "devices", "cihaz", "cihazlar", "anahtar",
}

# Extra generic words dropped only by the metadata/device-set matcher.
METADATA_GENERIC = GENERIC_TYPE_TOKENS | {
    "model", "models", "seri", "port", "ports",
}

# QWERTY adjacency (letters). Used to recognise realistic adjacent-key typos
# such as 'q' for 'w' (sq46 -> sw-46) or 'e' for 'w' (se46 -> sw-46).
QWERTY_ADJACENT = {
    "q": set("was"), "w": set("qeasd"), "e": set("wrdsf"), "r": set("etdfg"),
    "t": set("ryfgh"), "y": set("tughj"), "u": set("yihjk"), "i": set("uojkl"),
    "o": set("ipkl"), "p": set("ol"),
    "a": set("qwsxz"), "s": set("awedxz"), "d": set("serfcx"), "f": set("drtgvc"),
    "g": set("ftyhbv"), "h": set("gyujbn"), "j": set("huiknm"), "k": set("jiolm"),
    "l": set("kop"),
    "z": set("asx"), "x": set("zasdc"), "c": set("xdfv"), "v": set("cfgb"),
    "b": set("vghn"), "n": set("bhjm"), "m": set("njk"),
}

_CLITIC_RE = re.compile(r"[’'][^\W_]{0,4}$")
_TOKEN_RE = re.compile(r"[^\W_]+")  # unicode alnum runs (no underscore)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
def _strip_clitic(s):
    """Remove a trailing possessive clitic: sw-46'nin -> sw-46."""
    return _CLITIC_RE.sub("", s)


def normalize(s):
    """Compact a reference for comparison.

    Lowercases, strips a trailing possessive clitic, then removes whitespace,
    hyphens and underscores. Keeps unicode letters and digits.
    """
    if s is None:
        return ""
    s = _strip_clitic(str(s).lower().strip())
    s = re.sub(r"[\s\-_]+", "", s)
    return s


def _significant_tokens(s, generic):
    return [
        t for t in _TOKEN_RE.findall(_strip_clitic(str(s).lower()))
        if t not in generic
    ]


def _compact_query(q_raw):
    """Normalize a device reference, dropping generic type words.

    'core switch' -> 'core', 'sw 46' -> 'sw46', "sw-46'nin" -> 'sw46'.
    """
    return "".join(_significant_tokens(q_raw, GENERIC_TYPE_TOKENS))


# ---------------------------------------------------------------------------
# Small string helpers
# ---------------------------------------------------------------------------
def _numeric_suffix(s):
    m = re.search(r"(\d+)$", s)
    return m.group(1) if m else ""


def _leading_alpha(s):
    m = re.match(r"^[a-z]+", s)
    return m.group(0) if m else ""


def _damerau_levenshtein(a, b):
    """Optimal string alignment (Damerau-Levenshtein) distance."""
    n, m = len(a), len(b)
    maxdist = n + m
    d = [[0] * (m + 2) for _ in range(n + 2)]
    # Sentinel row/column; d[i+1][j+1] holds the distance between a[:i] and b[:j].
    d[0][0] = maxdist
    for i in range(n + 1):
        d[i + 1][0] = maxdist
        d[i + 1][1] = i
    for j in range(m + 1):
        d[0][j + 1] = maxdist
        d[1][j + 1] = j
    da = {}
    for i in range(1, n + 1):
        db = 0
        for j in range(1, m + 1):
            k = da.get(b[j - 1], 0)
            l = db
            cost = 0 if a[i - 1] == b[j - 1] else 1
            if cost == 0:
                db = j
            d[i + 1][j + 1] = min(
                d[i][j] + cost,        # substitution
                d[i][j + 1] + 1,       # insertion
                d[i + 1][j] + 1,       # deletion
                d[k][l] + (i - k - 1) + 1 + (j - l - 1),  # transposition
            )
        da[a[i - 1]] = i
    return d[n + 1][m + 1]


def _is_adjacent(a, b):
    return b in QWERTY_ADJACENT.get(a, set())


def _tok_match(qt, mt):
    """Query token matches a model/hostname token (equal or prefix, either way)."""
    return mt == qt or mt.startswith(qt) or qt.startswith(mt)


def _hostname_tokens(hostname):
    return _TOKEN_RE.findall(str(hostname).lower())


# ---------------------------------------------------------------------------
# Inventory loading / indexing
# ---------------------------------------------------------------------------
_DEFAULT_INDEX = None


def load_inventory(path=None):
    if path is None:
        path = os.path.join(HERE, "inventory.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_index(inventory):
    models = inventory.get("models", [])
    devices = inventory.get("devices", [])
    prefixes = set()
    for d in devices:
        p = _leading_alpha(normalize(d.get("hostname", "")))
        if p:
            prefixes.add(p)
    return {"models": models, "devices": devices, "prefixes": prefixes}


def get_index(inventory=None):
    global _DEFAULT_INDEX
    if inventory is not None:
        return build_index(inventory)
    if _DEFAULT_INDEX is None:
        _DEFAULT_INDEX = build_index(load_inventory())
    return _DEFAULT_INDEX


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------
def _resolved(device, reason, query=None, matched=None, match=None, models=None):
    out = {"outcome": "resolved", "reason": reason, "device": device, "candidates": []}
    if query is not None:
        out["query"] = query
    if matched is not None:
        out["matched"] = matched
    if match is not None:
        out["match"] = match
    if models is not None:
        out["models"] = models
    return out


def _ambiguous(devices, reason, candidate_details=None, models=None):
    out = {"outcome": "ambiguous", "reason": reason, "candidates": devices, "device": None}
    if candidate_details is not None:
        out["candidate_details"] = candidate_details
    if models is not None:
        out["models"] = models
    return out


def _no_match(extra=None):
    out = {"outcome": "no_match", "reason": "no_match", "candidates": []}
    if extra:
        out.update(extra)
    return out


# ---------------------------------------------------------------------------
# Typo candidate generation + scoring
# ---------------------------------------------------------------------------
def _score_typo(q, h, dist, q_suffix, q_prefix, known_prefixes):
    if dist == 0:
        return 100
    h_suffix = _numeric_suffix(h)
    h_prefix = _leading_alpha(h)

    if len(q) == len(h):
        mismatches = [(a, b) for a, b in zip(q, h) if a != b]
        if len(mismatches) == 2 and mismatches[0][0] == mismatches[1][1] and mismatches[0][1] == mismatches[1][0]:
            score = 70  # transposition
        elif len(mismatches) == 1:
            a, b = mismatches[0]
            score = 85 if _is_adjacent(a, b) else 60  # keyboard-adjacent substitution
        else:
            score = 55
    else:
        score = 75  # single insertion or deletion

    # Numeric suffix preservation: exact suffix is a strong positive signal,
    # an unrelated suffix is a penalty.
    if q_suffix and h_suffix:
        if q_suffix == h_suffix:
            score += 25
        elif not (q_suffix.startswith(h_suffix) or h_suffix.startswith(q_suffix)):
            score -= 20

    # Known hostname-prefix awareness.
    if q_prefix and q_prefix in known_prefixes and q_prefix == h_prefix:
        score += 10
    return score


def _generate_typo_candidates(q, idx):
    devices = idx["devices"]
    known_prefixes = idx["prefixes"]
    q_suffix = _numeric_suffix(q)
    q_prefix = _leading_alpha(q)
    best = {}
    for d in devices:
        h = normalize(d.get("hostname", ""))
        dist = _damerau_levenshtein(q, h)
        if dist <= MAX_EDIT_DISTANCE:
            score = _score_typo(q, h, dist, q_suffix, q_prefix, known_prefixes)
            cand = {"device": d, "score": score, "match_kind": "edit_distance",
                    "distance": dist, "hostname_norm": h}
        elif len(q) >= 2 and h.startswith(q):
            cand = {"device": d, "score": PREFIX_SCORE, "match_kind": "prefix",
                    "distance": dist, "hostname_norm": h}
        else:
            continue
        key = d["hostname"]
        if key not in best or cand["score"] > best[key]["score"]:
            best[key] = cand
    return sorted(best.values(), key=lambda c: (c["distance"], -c["score"]))


def _clearly_stronger(candidates):
    edit = [c for c in candidates if c.get("match_kind") == "edit_distance"]
    if not edit:
        return False  # prefix-only candidates never auto-resolve
    min_dist = min(c["distance"] for c in edit)
    at_min = [c for c in edit if c["distance"] == min_dist]
    if len(at_min) != 1:
        return False  # tie at minimum distance -> ambiguous
    top = at_min[0]
    if top["score"] < TYPO_CONFIDENCE_THRESHOLD:
        return False
    others = [c for c in candidates if c is not top]
    if others and (top["score"] - others[0]["score"]) < AUTO_RESOLVE_MARGIN:
        return False
    return True


# ---------------------------------------------------------------------------
# Metadata / model matching
# ---------------------------------------------------------------------------
def _model_tokens(model):
    parts = [
        model.get("brand", ""), model.get("sku", ""), model.get("model", ""),
        model.get("canonical_name", ""), model.get("search_text", ""),
    ]
    parts += model.get("aliases", []) or []
    text = " ".join(str(p) for p in parts)
    return _TOKEN_RE.findall(_strip_clitic(text.lower()))


def _metadata_significant_tokens(q_raw):
    return _significant_tokens(q_raw, METADATA_GENERIC)


def _metadata_match_models(q_raw, idx):
    toks = _metadata_significant_tokens(q_raw)
    if not toks:
        return []
    q = "".join(toks)
    matched = []
    for m in idx["models"]:
        ids = {
            normalize(m.get("sku", "")),
            normalize(m.get("model", "")),
            normalize(m.get("canonical_name", "")),
        }
        ids |= {normalize(a) for a in (m.get("aliases", []) or [])}
        if q in ids:
            matched.append(m)
            continue
        mtoks = _model_tokens(m)
        if all(any(_tok_match(t, mt) for mt in mtoks) for t in toks):
            matched.append(m)
    return matched


def _hostname_group_matches(device, toks):
    htoks = _hostname_tokens(device.get("hostname", ""))
    return all(any(_tok_match(t, ht) for ht in htoks) for t in toks)


def _matched_fields(q_raw, matched_models, group_devices):
    fields = set()
    if group_devices:
        fields.add("hostname")
    toks = set(_metadata_significant_tokens(q_raw))
    q = "".join(_metadata_significant_tokens(q_raw))
    for m in matched_models:
        if q == normalize(m.get("sku", "")):
            fields.add("sku")
        if q == normalize(m.get("model", "")):
            fields.add("model")
        if q == normalize(m.get("canonical_name", "")):
            fields.add("canonical_name")
        if any(q == normalize(a) for a in (m.get("aliases", []) or [])):
            fields.add("alias")
        brand = normalize(m.get("brand", ""))
        if any(_tok_match(t, brand) for t in toks):
            fields.add("brand")
    return sorted(fields)


# ---------------------------------------------------------------------------
# Public API: single-device resolution
# ---------------------------------------------------------------------------
def resolve_device(query, inventory=None):
    """Resolve a single-device reference.

    Returns a dict with outcome in {resolved, ambiguous, no_match}, a reason
    from the closed set, and either device (resolved), candidates (ambiguous),
    or empty candidates (no_match).
    """
    idx = get_index(inventory)
    devices = idx["devices"]

    if query is None or not str(query).strip():
        return _no_match()
    q_raw = str(query).strip()
    q = _compact_query(q_raw)
    if not q:
        return _no_match()

    # 1) exact hostname (case-insensitive literal)
    exact = [d for d in devices if str(d["hostname"]).lower() == q_raw.lower()]
    if len(exact) == 1:
        return _resolved(exact[0], "exact", query=q_raw, matched=exact[0]["hostname"])
    if len(exact) > 1:
        return _ambiguous(exact, "ambiguous")

    # 2) normalized hostname
    norm = [d for d in devices if normalize(d["hostname"]) == q]
    if len(norm) == 1:
        return _resolved(norm[0], "normalized", query=q_raw, matched=norm[0]["hostname"])
    if len(norm) > 1:
        return _ambiguous(norm, "ambiguous")

    # 3) alias (device-level)
    alias = []
    for d in devices:
        for a in (d.get("aliases", []) or []):
            if normalize(a) == q or str(a).lower() == q_raw.lower():
                alias.append(d)
                break
    alias = _dedupe(alias)
    if len(alias) == 1:
        return _resolved(alias[0], "alias", query=q_raw, matched=alias[0]["hostname"])
    if len(alias) > 1:
        return _ambiguous(alias, "ambiguous")

    # 4) typo candidates (never blind-pick)
    cands = _generate_typo_candidates(q, idx)
    if cands:
        if _clearly_stronger(cands):
            top = cands[0]
            return _resolved(top["device"], "typo", query=q_raw, match={
                "matched": top["device"]["hostname"], "distance": top["distance"],
                "score": top["score"], "match_kind": top["match_kind"],
            })
        return _ambiguous([c["device"] for c in cands], "ambiguous", candidate_details=cands)

    # 5) metadata single-device
    models = _metadata_match_models(q_raw, idx)
    if models:
        skus = {normalize(m.get("sku", "")) for m in models}
        devs = _dedupe([d for d in devices if normalize(d.get("sku", "")) in skus])
        if len(devs) == 1:
            return _resolved(devs[0], "metadata", query=q_raw, models=models)
        if len(devs) > 1:
            return _ambiguous(devs, "ambiguous", models=models)
        return _no_match({"models": models})

    return _no_match()


def _dedupe(devices):
    seen = set()
    out = []
    for d in devices:
        h = d.get("hostname")
        if h not in seen:
            seen.add(h)
            out.append(d)
    return out


# ---------------------------------------------------------------------------
# Public API: device-set / filter resolution
# ---------------------------------------------------------------------------
def resolve_device_set(query, inventory=None):
    """Filter the inventory for a model/group reference.

    Returns every matching model (catalog entries) and every matching device.
    This is a filter, so it never picks a single winner when several match.
    """
    idx = get_index(inventory)
    devices = idx["devices"]

    if query is None or not str(query).strip():
        return {"outcome": "no_match", "reason": "no_match", "models": [], "devices": []}
    q_raw = str(query).strip()

    matched_models = _metadata_match_models(q_raw, idx)
    toks = _metadata_significant_tokens(q_raw)
    group_devices = [d for d in devices if toks and _hostname_group_matches(d, toks)]

    skus = {normalize(m.get("sku", "")) for m in matched_models}
    model_devices = [d for d in devices if normalize(d.get("sku", "")) in skus]

    all_devices = _dedupe(model_devices + group_devices)

    if not matched_models and not all_devices:
        return {"outcome": "no_match", "reason": "no_match", "models": [], "devices": []}

    return {
        "outcome": "resolved",
        "reason": "metadata",
        "models": matched_models,
        "devices": all_devices,
        "matched_fields": _matched_fields(q_raw, matched_models, group_devices),
    }


# ---------------------------------------------------------------------------
# Status lookup + deterministic formatters
# ---------------------------------------------------------------------------
def _status_str(status):
    s = str(status).lower().strip()
    if s in ("up", "1", "active", "online", "ayakta"):
        return "up"
    if s in ("down", "0", "inactive", "offline", "kapalı"):
        return "down"
    if s in ("unknown", "", "none", "null", "bilinmiyor"):
        return "unknown"
    return s


def lookup_status(hostname, inventory=None):
    idx = get_index(inventory)
    for d in idx["devices"]:
        if d.get("hostname") == hostname:
            return _status_str(d.get("status"))
    return None


def format_atomic(hostname, status):
    s = _status_str(status)
    if s == "up":
        return hostname + " şu anda çalışıyor."
    if s == "down":
        return hostname + " şu anda çalışmıyor."
    if s == "unknown":
        return hostname + " durumu bilinmiyor."
    return hostname + " durumu: " + str(status)


def format_clarification(candidates):
    names = [d["hostname"] for d in (candidates or [])]
    if not names:
        return "Eşleşen cihaz bulunamadı."
    return "Hangi cihazı kastettiğinizi netleştirir misiniz? Adaylar: " + ", ".join(names) + "."


def format_device_set(result):
    models = result.get("models") or []
    devices = result.get("devices") or []
    parts = []
    if models:
        names = ", ".join(m.get("canonical_name", m.get("sku", "")) for m in models)
        parts.append("Model(ler): " + names)
    if devices:
        rows = ", ".join(d["hostname"] + " (" + _status_str(d.get("status")) + ")" for d in devices)
        parts.append("Cihazlar: " + rows)
    if not parts:
        return "Eşleşen model/cihaz bulunamadı."
    return " ".join(parts) + "."


if __name__ == "__main__":
    import sys
    for q in sys.argv[1:]:
        r = resolve_device(q)
        print(q, "->", json.dumps(r, ensure_ascii=False, default=str))
