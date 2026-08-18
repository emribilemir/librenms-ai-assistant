#!/usr/bin/env python3
"""Offline deterministic tests for resolver.py (no LLM, no network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import resolver as R  # noqa: E402

PASS = 0
FAIL = []


def check(desc, cond):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(desc)
        print("FAIL: " + desc)


def hostname(r):
    if r.get("device"):
        return r["device"]["hostname"]
    return None


def candidate_hosts(r):
    return sorted(c["hostname"] for c in (r.get("candidates") or []))


def model_skus(r):
    return sorted(m["sku"] for m in (r.get("models") or []))


def device_hosts(r):
    return sorted(d["hostname"] for d in (r.get("devices") or []))


# --- exact hostname ---
check("exact sw-46", (lambda r: r["outcome"] == "resolved" and r["reason"] == "exact" and hostname(r) == "sw-46")(R.resolve_device("sw-46")))
check("exact case SW-46 -> sw-46", hostname(R.resolve_device("SW-46")) == "sw-46")
check("exact core-sw-01", hostname(R.resolve_device("core-sw-01")) == "core-sw-01")
check("exact sw-460 distinct", hostname(R.resolve_device("sw-460")) == "sw-460")
check("exact sw-47 distinct", hostname(R.resolve_device("sw-47")) == "sw-47")

# --- normalized (case/separator/clitic) ---
for q in ["Sw46", "sw46", "sw 46", "sw_46", "sw-46'nın"]:
    r = R.resolve_device(q)
    check("normalized %r -> sw-46" % q, r["outcome"] == "resolved" and r["reason"] == "normalized" and hostname(r) == "sw-46")

# --- alias ---
check("device alias core1 -> core-sw-01", hostname(R.resolve_device("core1")) == "core-sw-01" and R.resolve_device("core1")["reason"] == "alias")
check("device alias core-1 -> core-sw-01", hostname(R.resolve_device("core-1")) == "core-sw-01")

# --- safe keyboard typo ---
for q in ["sq46", "se46", "sww46"]:
    r = R.resolve_device(q)
    check("typo %r -> sw-46" % q, r["outcome"] == "resolved" and r["reason"] == "typo" and hostname(r) == "sw-46")

# --- unsafe / ambiguous fuzzy ---
r = R.resolve_device("sw466")
check("sw466 ambiguous", r["outcome"] == "ambiguous" and candidate_hosts(r) == ["sw-46", "sw-460"])
r = R.resolve_device("sw4")
check("sw4 ambiguous (>=4 candidates)", r["outcome"] == "ambiguous" and {"sw-46", "sw-47", "sw-48", "sw-460"} <= set(candidate_hosts(r)))
r = R.resolve_device("core")
check("core ambiguous", r["outcome"] == "ambiguous" and candidate_hosts(r) == ["core-sw-01", "core-sw-02"])
r = R.resolve_device("core switch")
check("core switch ambiguous", r["outcome"] == "ambiguous" and candidate_hosts(r) == ["core-sw-01", "core-sw-02"])

# --- no_match ---
for q in ["depo switch", "xyz-999", "firewall-01", "sw-99", "unknown-device", "", None]:
    r = R.resolve_device(q)
    check("no_match %r" % q, r["outcome"] == "no_match" and r["reason"] == "no_match" and not r["candidates"])

# --- metadata single device ---
r = R.resolve_device("J9775A")
check("metadata single J9775A -> sw-2530-48", r["outcome"] == "resolved" and r["reason"] == "metadata" and hostname(r) == "sw-2530-48")
r = R.resolve_device("2530-24G")
check("metadata single 2530-24G -> sw-2530-24", r["outcome"] == "resolved" and r["reason"] == "metadata" and hostname(r) == "sw-2530-24")

# --- metadata multi-device stays ambiguous (single-device path) ---
r = R.resolve_device("J9772A")
check("metadata multi-device J9772A -> ambiguous", r["outcome"] == "ambiguous" and set(candidate_hosts(r)) == {"sw-46", "sw-47", "sw-48", "sw-460"})

# --- device-set: exact SKU ---
r = R.resolve_device_set("J9772A")
check("set SKU J9772A models", r["outcome"] == "resolved" and model_skus(r) == ["J9772A"])
check("set SKU J9772A devices", set(device_hosts(r)) == {"sw-46", "sw-47", "sw-48", "sw-460"})

# --- device-set: broader model text (multi-match) ---
r = R.resolve_device_set("2530 48G")
check("set 2530 48G multi-model", model_skus(r) == ["J9772A", "J9775A"])
check("set 2530 48G devices", {"sw-46", "sw-47", "sw-48", "sw-460", "sw-2530-48"} <= set(device_hosts(r)))

# --- device-set: feature-style metadata query (multi-match) ---
r = R.resolve_device_set("48 port PoE ProCurve")
check("set 48 port PoE ProCurve multi-model", model_skus(r) == ["J9772A", "JL357A"])
check("set 48 port PoE ProCurve devices", {"sw-46", "sw-47", "sw-48", "sw-460", "sw-2540-48"} <= set(device_hosts(r)))

# --- device-set: catalog alias ---
r = R.resolve_device_set("HP ProCurve 2530-48G-PoEP")
check("set catalog alias -> J9772A", model_skus(r) == ["J9772A"])

# --- device-set: group (hostname) ---
r = R.resolve_device_set("core switch")
check("set core switch group devices", set(device_hosts(r)) == {"core-sw-01", "core-sw-02"})

# --- status lookup + formatters ---
check("lookup sw-46 up", R.lookup_status("sw-46") == "up")
check("lookup sw-47 down", R.lookup_status("sw-47") == "down")
check("lookup sw-48 unknown", R.lookup_status("sw-48") == "unknown")
check("lookup sw-99 none", R.lookup_status("sw-99") is None)
check("format up", "çalışıyor" in R.format_atomic("sw-46", "up"))
check("format down", "çalışmıyor" in R.format_atomic("sw-47", "down"))
check("format unknown", "bilinmiyor" in R.format_atomic("sw-48", "unknown"))
check("format integer status 1 -> up", "çalışıyor" in R.format_atomic("sw-46", 1))
check("format clarification lists candidates", "sw-46" in R.format_clarification([{"hostname": "sw-46"}, {"hostname": "sw-460"}]) and "sw-460" in R.format_clarification([{"hostname": "sw-46"}, {"hostname": "sw-460"}]))
r = R.resolve_device_set("J9772A")
txt = R.format_device_set(r)
check("format device_set mentions model + device", "J9772A 2530-48G-PoEP" in txt and "sw-46" in txt)

print("")
print("PASS=%d FAIL=%d" % (PASS, len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  - " + f)
    sys.exit(1)
print("ALL TESTS PASSED")
