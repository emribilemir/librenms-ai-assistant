# Semantic Planner Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Türkçe regex/kelime tabanlı planner yolunu kaldırmak, Qwen planını katı biçimde doğrulamak ve backend çağrısı olmayan device-set cevaplarından operasyonel durum bilgisini çıkarmak.

**Architecture:** Qwen doğal dili tek bir structured plana çevirir; Python yalnızca plan sözleşmesini doğrular. Resolver v5 açık kimlikleri ve structured katalog filtrelerini çözer, backend canlı gerçeklerin tek kaynağı olarak kalır. RAG bu planda uygulanmaz.

**Tech Stack:** Python 3, standard-library `unittest`, mevcut Ollama structured-output istemcisi, resolver v5 ve dummy SpyBackend.

**Spec:** `docs/superpowers/specs/2026-08-26-semantic-planner-deterministic-core-rag-design.md`

## Global Constraints

- Tam Gold, Generated, Legacy veya LLM suite çalıştırılmayacak.
- `librenms-planner-v3-poc/`, `CONTEXT.md` ve `.DS_Store` değiştirilmeyecek.
- RAG, embedding, vector database, `speed_mbps` ve multi-device fan-out eklenmeyecek.
- Python doğal dil intent veya facet extraction yapmayacak.
- Plan doğrulama başarısızsa resolver/backend çağrısı yapılmayacak.
- Device-set cevapları backend çağrısı olmadan operasyonel status yazmayacak.

---

### Task 1: Semantic Plan Contract

**Files:**
- Modify: `librenms-hybrid-poc/planner_v2.py`
- Create: `librenms-hybrid-poc/test_semantic_planner.py`

**Interfaces:**
- Consumes: Qwen'den parse edilmiş `dict` planı.
- Produces: `normalize_plan_filters(plan: dict) -> dict` ve `validate_plan(plan: object) -> tuple[bool, list[str]]`.

- [ ] **Step 1: Failing contract tests yaz**

`librenms-hybrid-poc/test_semantic_planner.py` içinde gerçek `planner_v2` modülünü import edip aşağıdaki davranışları test et:

```python
import unittest

import planner_v2


class SemanticPlanContractTests(unittest.TestCase):
    def test_accepts_valid_device_set_plan(self):
        plan = {
            "request_type": "device_set",
            "intent": "device_set",
            "device_query": None,
            "device_filters": {
                "brand": "HP ProCurve",
                "family": "2530",
                "port_count": 48,
                "poe": False,
            },
        }
        self.assertEqual(planner_v2.validate_plan(plan), (True, []))

    def test_rejects_route_intent_mismatch(self):
        plan = {
            "request_type": "ports",
            "intent": "device_set",
            "device_query": "J9774A",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("request_type 'ports' requires intent 'device_ports'", errors)

    def test_rejects_product_filters_on_non_device_set_route(self):
        plan = {
            "request_type": "atomic_fact",
            "intent": "device_status",
            "device_query": "J9774A",
            "device_filters": {
                "brand": None,
                "family": None,
                "port_count": 48,
                "poe": None,
            },
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn(
            "non-device_set route must not contain product filters: port_count",
            errors,
        )

    def test_rejects_empty_device_set(self):
        plan = {
            "request_type": "device_set",
            "intent": "device_set",
            "device_query": None,
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn(
            "device_set must contain a device_query or at least one filter",
            errors,
        )

    def test_rejects_missing_filter_field(self):
        plan = {
            "request_type": "atomic_fact",
            "intent": "device_status",
            "device_query": "J9774A",
            "device_filters": {"brand": None, "family": None, "port_count": None},
        }
        valid, errors = planner_v2.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn(
            "device_filters must contain exactly: brand, family, port_count, poe",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: RED doğrulaması**

Run: `python3 librenms-hybrid-poc/test_semantic_planner.py -v`

Expected: FAIL; `planner_v2` henüz `validate_plan` sağlamıyor.

- [ ] **Step 3: Minimal semantic contract uygula**

`planner_v2.py` içindeki `_WORD_RE`, `_PORT_COUNT_RE`, `_PORT_SPEED_RE`, `_SET_CUES`, `_POE_FALSE_RE`, `_POE_TRUE_RE`, `_words`, `_compact`, `_has_set_cue`, `_extract_port_count`, `_extract_poe`, `_family_in_query`, `_literal_occurrence`, `_catalog_reference`, `_brand_from_query` ve `try_deterministic_device_set_plan` kodlarını kaldır.

Dosyada `DEVICE_FILTER_SCHEMA`, `EMPTY_FILTERS`, route/intent enumları, `normalize_plan_filters` ve aşağıdaki sözleşme doğrulayıcısı kalsın:

```python
REQUEST_TYPES = (
    "atomic_fact", "ports", "alerts", "events", "device_set",
    "investigation", "historical_investigation", "unsupported",
)

INTENTS = (
    "device_status", "device_ports", "device_alerts", "device_events",
    "device_set", "investigation", "historical_status", "unsupported", "unknown",
)

ROUTE_TO_INTENT = {
    "atomic_fact": "device_status",
    "ports": "device_ports",
    "alerts": "device_alerts",
    "events": "device_events",
    "device_set": "device_set",
    "investigation": "investigation",
    "historical_investigation": "historical_status",
}


def validate_plan(plan):
    errors = []
    if not isinstance(plan, dict):
        return False, ["planner output is not a JSON object"]

    required = ("request_type", "intent", "device_query", "device_filters")
    for key in required:
        if key not in plan:
            errors.append(f"missing required field: {key}")

    rt = plan.get("request_type")
    intent = plan.get("intent")
    device_query = plan.get("device_query")
    filters = plan.get("device_filters")

    if rt not in REQUEST_TYPES:
        errors.append(f"invalid request_type: {rt!r}")
    if intent not in INTENTS:
        errors.append(f"invalid intent: {intent!r}")
    if device_query is not None and not isinstance(device_query, str):
        errors.append("device_query must be string or null")

    if not isinstance(filters, dict):
        errors.append("device_filters must be an object")
    else:
        if set(filters) != set(EMPTY_FILTERS):
            errors.append("device_filters must contain exactly: brand, family, port_count, poe")
        brand = filters.get("brand")
        family = filters.get("family")
        port_count = filters.get("port_count")
        poe = filters.get("poe")
        if brand is not None and not isinstance(brand, str):
            errors.append("device_filters.brand must be string or null")
        if family is not None and not isinstance(family, str):
            errors.append("device_filters.family must be string or null")
        if port_count is not None and (
            isinstance(port_count, bool) or not isinstance(port_count, int) or port_count < 1
        ):
            errors.append("device_filters.port_count must be positive integer or null")
        if poe is not None and not isinstance(poe, bool):
            errors.append("device_filters.poe must be boolean or null")

    expected_intent = ROUTE_TO_INTENT.get(rt)
    if expected_intent and intent != expected_intent:
        errors.append(f"request_type {rt!r} requires intent {expected_intent!r}")

    if rt != "device_set" and isinstance(filters, dict):
        non_null = [key for key, value in filters.items() if value is not None]
        if non_null:
            errors.append(
                "non-device_set route must not contain product filters: "
                + ", ".join(non_null)
            )

    if rt == "device_set" and isinstance(filters, dict):
        has_query = isinstance(device_query, str) and bool(device_query.strip())
        if not has_query and not any(value is not None for value in filters.values()):
            errors.append("device_set must contain a device_query or at least one filter")

    return not errors, errors
```

- [ ] **Step 4: GREEN doğrulaması**

Run: `python3 librenms-hybrid-poc/test_semantic_planner.py -v`

Expected: 5 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add librenms-hybrid-poc/planner_v2.py librenms-hybrid-poc/test_semantic_planner.py
git commit -m "refactor: limit planner Python to schema validation"
```

### Task 2: Orchestrator Validation and Structured Filtering

**Files:**
- Modify: `librenms-hybrid-poc/hybrid_poc.py`
- Modify: `librenms-hybrid-poc/test_semantic_planner.py`

**Interfaces:**
- Consumes: `ollama_chat()` tarafından döndürülen structured planner JSON'u.
- Produces: yalnızca doğrulanmış planı resolver v5'e ileten `orchestrate()` trace'i.

- [ ] **Step 1: Failing orchestration tests yaz**

Test dosyasına import helpers ekleyip gerçek `hybrid_poc`, resolver v5, dummy inventory ve SpyBackend kullan. Yalnız dış Ollama çağrısını `unittest.mock.patch` ile değiştir.

```python
import importlib.util
import json
import os
from unittest.mock import patch

import hybrid_poc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(ROOT, "hybrid-gold-v3")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver_v5 = load_module("resolver_v5_test", os.path.join(GOLD, "resolver_candidate_v5.py"))
dummy_backend = load_module("dummy_backend_test", os.path.join(GOLD, "dummy_backend.py"))
with open(os.path.join(GOLD, "dummy_inventory.json"), encoding="utf-8") as stream:
    INVENTORY = json.load(stream)


class OrchestratorSemanticPlannerTests(unittest.TestCase):
    def test_qwen_plan_filters_device_set_through_resolver_v5(self):
        plan = {
            "request_type": "device_set",
            "intent": "device_set",
            "device_query": None,
            "device_filters": {
                "brand": "HP ProCurve",
                "family": "2530",
                "port_count": 48,
                "poe": False,
            },
        }
        backend = dummy_backend.SpyBackend()
        with patch.object(
            hybrid_poc,
            "ollama_chat",
            return_value=(json.dumps(plan), "stop", 1.0),
        ):
            trace = hybrid_poc.orchestrate(
                "PoE'siz 48 port 2530 cihazları",
                inventory=INVENTORY,
                backend=backend,
                planner_schema="gold",
                resolver_module=resolver_v5,
            )
        self.assertTrue(trace["planner_llm_called"])
        self.assertEqual(trace["planner_output"]["raw"]["method"], "llm")
        self.assertEqual(trace["route"], "device_set")
        self.assertEqual(
            {model["sku"] for model in trace["resolver_output"]["models"]},
            {"J9775A"},
        )
        self.assertEqual(trace["tool_calls"], [])

    def test_invalid_plan_stops_before_resolver_and_backend(self):
        invalid = {
            "request_type": "ports",
            "intent": "device_set",
            "device_query": "J9774A",
            "device_filters": dict(planner_v2.EMPTY_FILTERS),
        }
        backend = dummy_backend.SpyBackend()
        with patch.object(
            hybrid_poc,
            "ollama_chat",
            return_value=(json.dumps(invalid), "stop", 1.0),
        ):
            trace = hybrid_poc.orchestrate(
                "J9774A portlarını göster",
                inventory=INVENTORY,
                backend=backend,
                planner_schema="gold",
                resolver_module=resolver_v5,
            )
        self.assertTrue(trace["planner_failure"])
        self.assertEqual(trace["route"], "unknown")
        self.assertIn("request_type 'ports' requires intent 'device_ports'", trace["planner_errors"])
        self.assertEqual(trace["tool_calls"], [])
```

- [ ] **Step 2: RED doğrulaması**

Run: `python3 librenms-hybrid-poc/test_semantic_planner.py -v`

Expected: İlk orchestration testi `try_deterministic_device_set_plan` kaldırıldığı için hata verir veya eski deterministic yola girer; ikinci test geçersiz planın halen çalıştırıldığını göstererek fail olur.

- [ ] **Step 3: Minimal orchestrator değişikliği uygula**

`hybrid_poc.orchestrate()` içinde deterministic planner çağrısını ve iki dallı plan oluşturmayı kaldır. Gold ve PoC schema yollarında `ollama_chat()` her zaman planner olarak çağrılsın. Gold plan parse edildikten sonra ham plan normalize edilmeden önce doğrulansın:

```python
valid, planner_errors = planner_v2.validate_plan(plan)
if not valid:
    plan = None
```

Bu sıra zorunludur: eksik `device_filters` anahtarları normalization ile gizlenmemelidir. Geçerli plan exact schema'yı zaten sağladığı için orchestrator normalization yapmaz. Planner raw method daima `"llm"` olsun. Planner-failure trace'ine `planner_errors` alanını ekle; başarılı trace'te de gözlemlenebilirlik için boş liste olarak döndür. Invalid planda resolver ve backend'e geçme.

- [ ] **Step 4: GREEN doğrulaması**

Run: `python3 librenms-hybrid-poc/test_semantic_planner.py -v`

Expected: 7 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add librenms-hybrid-poc/hybrid_poc.py librenms-hybrid-poc/test_semantic_planner.py
git commit -m "refactor: route all language through semantic planner"
```

### Task 3: Device-Set Output Truth Boundary

**Files:**
- Modify: `hybrid-gold-v3/resolver_candidate_v5.py`
- Modify: `librenms-hybrid-poc/test_semantic_planner.py`

**Interfaces:**
- Consumes: resolver v5 device-set sonucu.
- Produces: model ve hostname listesi; backend çağrısı yoksa operasyonel status içermez.

- [ ] **Step 1: Failing formatter test yaz**

`SemanticPlanContractTests` veya ayrı `DeviceSetFormattingTests` sınıfına ekle:

```python
def test_device_set_formatter_does_not_claim_inventory_status(self):
    result = {
        "outcome": "resolved",
        "models": [{"sku": "J9775A", "canonical_name": "J9775A 2530-48G"}],
        "devices": [{"hostname": "lab-j9775a-01", "status": "up"}],
        "unevaluated_count": 0,
        "unevaluated_fields": [],
    }
    text = resolver_v5.format_device_set(result)
    self.assertIn("J9775A 2530-48G", text)
    self.assertIn("lab-j9775a-01", text)
    self.assertNotIn("(up)", text)
```

- [ ] **Step 2: RED doğrulaması**

Run: `python3 librenms-hybrid-poc/test_semantic_planner.py -v`

Expected: FAIL; mevcut formatter `lab-j9775a-01 (up)` üretir.

- [ ] **Step 3: Minimal formatter değişikliği uygula**

`resolver_candidate_v5.format_device_set()` içinde `_v4.format_device_set(result)` çağrısını kullanma. Model canonical name'lerini ve cihaz hostname'lerini status olmadan biçimlendir; mevcut `unevaluated_count` açıklamasını koru:

```python
parts = []
if models:
    names = ", ".join(model.get("canonical_name", model.get("sku", "")) for model in models)
    parts.append("Model(ler): " + names)
if devices:
    hostnames = ", ".join(device["hostname"] for device in devices)
    parts.append("Cihazlar: " + hostnames)
text = " ".join(parts) + "." if parts else "Eşleşen model/cihaz bulunamadı."
```

- [ ] **Step 4: GREEN ve syntax doğrulaması**

Run: `python3 librenms-hybrid-poc/test_semantic_planner.py -v`

Expected: 8 tests, OK.

Run: `python3 -m py_compile librenms-hybrid-poc/planner_v2.py librenms-hybrid-poc/hybrid_poc.py hybrid-gold-v3/resolver_candidate_v5.py`

Expected: exit 0, output yok.

- [ ] **Step 5: Kapsam kontrolü**

Run: `git diff --check HEAD~2..HEAD -- librenms-hybrid-poc/planner_v2.py librenms-hybrid-poc/hybrid_poc.py hybrid-gold-v3/resolver_candidate_v5.py librenms-hybrid-poc/test_semantic_planner.py`

Expected: exit 0.

Run: `git status --short`

Expected: yalnızca kullanıcıya ait önceden var olan `.DS_Store`, `CONTEXT.md` ve `librenms-planner-v3-poc/` görünür; görev dosyaları temizdir.

- [ ] **Step 6: Commit**

```bash
git add hybrid-gold-v3/resolver_candidate_v5.py librenms-hybrid-poc/test_semantic_planner.py
git commit -m "fix: keep device-set status backend-owned"
```
