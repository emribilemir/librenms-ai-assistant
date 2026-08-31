# LibreNMS Natural Language — Planner / Catalog / Resolver Ownership Review

> **Status:** Proposed architecture direction for review  
> **Purpose:** This document does not declare the architecture final. It records the current direction, the problem we observed in the existing planner implementation, and the ownership model that should be evaluated before the next regression cycle.

## Context

The project is a read-only natural-language layer over LibreNMS.

The intended product is not simply "an LLM in front of LibreNMS". The system should route each request to the right kind of logic:

- natural-language intent understanding where language understanding is actually needed,
- deterministic catalog parsing and identity resolution where the data is structured,
- deterministic backend/tool execution for factual retrieval,
- LLM synthesis only for bounded investigation cases,
- deterministic validation for grounding and safety.

The current v5 work already introduced:

- catalog ingestion into structured metadata,
- generic identity variants,
- structured device filters,
- resolver-side ambiguity preservation,
- UNKNOWN/null handling for catalog fields that cannot be parsed safely,
- deterministic atomic retrieval,
- fixed Level-1 investigation evidence collection.

During regression work, however, the planner started accumulating keyword/stem rules that were also making request-type decisions.

Examples included concepts such as:

```python
_RETRIEVAL_STEMS = ("port", "alarm", "event", "log")
_SET_NOUN_STEMS = ("cihaz", "switch", "model", "procurve", "olan")
_ACTION_STEMS = ("goster", "göster", "getir", "listele")
```

These rules improved some test results, but they also blurred architectural ownership.

The concern is not that deterministic parsing or regex is inherently wrong. The concern is **what it is allowed to decide**.

---

## Problem

There are two different questions in a natural-language monitoring request:

1. **What does the user want to do?**
2. **What device, model, family, or catalog subset is the user referring to?**

Those are different responsibilities.

For example:

```text
J9774A loglarını göster
```

The important intent decision is:

```text
request_type = events
```

But:

```text
2530 48G cihazları
```

requires understanding that:

```text
2530 -> family
48G  -> catalog/device facet
```

Likewise:

```text
48G açık mı?
```

should not require the catalog parser to decide whether this is a status request.

The language planner should understand that the user is asking for **status**.

The deterministic catalog layer should understand what **48G** refers to.

If the matching catalog constraints identify one physical device, the backend can return its status.

If they identify multiple devices, the resolver should return clarification rather than choosing one arbitrarily.

---

# Proposed Ownership Model

## 1. Qwen Planner Owns Intent

The planner answers:

> **What is the user asking the system to do?**

Example request types may include:

```text
atomic_fact
ports
alerts
events
device_set
investigation
historical_investigation
unsupported
```

The planner should not need to know every SKU, model, or catalog variation.

It should produce the semantic operation requested by the user.

Examples:

```text
"J9774A açık mı?"
-> atomic_fact / device_status

"J9774A loglarını göster"
-> events / device_events

"48G açık mı?"
-> atomic_fact / device_status

"48G cihazları göster"
-> device_set
```

This is the natural-language responsibility.

---

## 2. Deterministic Catalog Parser Owns Referent Semantics

The catalog layer answers:

> **What device identity or structured catalog constraints did the user refer to?**

This layer may legitimately use:

- catalog-derived values,
- regex,
- normalization,
- aliases,
- deterministic morphology handling,
- SKU/model variants,
- structured domain grammar.

Examples:

```text
48 port
-> port_count = 48

48G
-> port_count = 48
-> speed = 1G, if represented by the schema/catalog

PoE
-> poe = true

PoE olmayan
-> poe = false

2530
-> family = 2530

J9772A
-> explicit SKU identity

2530-48G-PoEP
-> explicit model identity
```

This deterministic behavior is desirable because these are structured catalog semantics rather than general conversational intent.

### Important distinction

This is acceptable:

```text
48G -> port_count = 48
```

This is not the desired architecture:

```text
"log" exists -> therefore request_type = events
"switchleri" exists -> therefore request_type = device_set
"olan" exists -> therefore request_type = device_set
```

The first is domain parsing.

The second is a handwritten intent classifier.

---

## 3. Resolver Owns Identity Resolution

The resolver receives:

- an explicit identity reference, and/or
- structured catalog constraints.

It should not parse free-form Turkish intent.

Its responsibility is:

```text
structured reference
        |
        v
unique match / ambiguous match / no match
```

Examples:

```text
J9772A
-> exact SKU lookup
-> if two physical devices use the SKU:
   clarification

9772A
-> catalog identity variant
-> if ambiguous:
   clarification

family=2530, port_count=48, poe=null
-> return every matching model/device
```

The resolver must never choose one device merely because it is the highest fuzzy match when the request remains materially ambiguous.

---

## 4. Backend Owns Facts

The backend controls what can actually be asserted.

Examples:

```text
device status
ports
alerts
events
```

For atomic queries, the answer should be produced deterministically from backend data whenever possible.

The LLM should not invent or reinterpret an atomic fact that the backend already provides directly.

---

## 5. Investigation Remains Bounded

Investigation continues to use the fixed Level-1 evidence bundle:

```text
get_device
get_ports
get_alerts
get_events
```

The LLM may interpret this evidence, but it should not expand the investigation recursively or invoke arbitrary tools.

A later architecture step should introduce:

- structured findings,
- stable evidence references,
- deterministic grounding validation.

That work is separate from the planner ownership decision described here.

---

# Desired End-to-End Flow

```text
User Query
   |
   v
Qwen Planner
"What does the user want?"
   |
   | request_type / intent
   v
Deterministic Catalog Understanding
"What does the referenced device/model/facet mean?"
   |
   | explicit identity
   | structured filters
   v
Resolver v5
"Which device(s) does this identify?"
   |
   | unique
   | ambiguous
   | no match
   v
Backend / Fixed Evidence Collection
   |
   v
Deterministic Response
or
Bounded LLM Synthesis
```

A useful shorthand for the ownership boundary is:

> **Qwen = intent**  
> **Catalog parser = referent semantics**  
> **Resolver = identity resolution**  
> **Backend = truth**

---

# Examples to Evaluate

These examples are not intended as production hardcodes. They are architecture examples that should generalize.

## Status from exact identity

```text
J9774A açık mı?
```

Expected conceptual flow:

```text
planner:
  request_type = atomic_fact
  intent = device_status

catalog/reference:
  identity = J9774A

resolver:
  unique device

backend:
  get_device

response:
  current status
```

---

## Status from a catalog facet

```text
48G açık mı?
```

Expected behavior:

```text
planner:
  request_type = atomic_fact
  intent = device_status

catalog parser:
  port_count = 48
  speed = 1G

resolver:
  if exactly one physical device matches:
      resolve
  if multiple devices match:
      clarification
  if none:
      no_match
```

The system should not choose an arbitrary 48G device.

---

## Device-set discovery

```text
2530 48G cihazları
```

Expected structured referent:

```json
{
  "device_query": null,
  "device_filters": {
    "family": "2530",
    "port_count": 48,
    "poe": null
  }
}
```

PoE must remain unconstrained if the user did not ask for it.

Therefore both PoE and non-PoE 48-port models may match.

---

## Explicit model identity

```text
2530-48G-PoEP açık mı?
```

Expected behavior:

```text
planner:
  status request

catalog parser:
  explicit model identity

resolver:
  one physical instance -> resolve
  multiple physical instances -> clarification
```

The canonical model token should not be broken apart into broad facets if the user clearly supplied the exact model identity.

---

## Resource retrieval

```text
J9774A loglarını göster
```

Expected behavior:

```text
planner:
  events

catalog/reference:
  J9774A

resolver:
  resolve identity

backend:
  get_device
  get_events
```

No Python keyword rule should be responsible for deciding that the request is an events request.

---

# Architecture Invariants

The implementation should preserve the following invariants:

1. **Intent ownership remains in the planner.**
2. **Catalog parsing does not change request type.**
3. **Resolver does not become a natural-language parser.**
4. **Catalog shorthand can be used for more than device-set queries.**
5. **Exact identities remain exact identities.**
6. **Structured facets remain structured facets.**
7. **UNKNOWN catalog metadata is not guessed.**
8. **Ambiguous identity remains ambiguous.**
9. **Atomic facts remain deterministic.**
10. **Investigation remains fixed Level-1 and read-only.**
11. **No test-specific query literal is added to production logic.**
12. **Regression failures should expose missing capabilities, not trigger isolated phrase patches.**

---

# What Should Be Evaluated Before Implementation Is Frozen

The next review should answer these questions.

### Planner boundary

- Is Qwen sufficiently reliable at request-type classification when catalog parsing no longer short-circuits intent?
- Should deterministic intent classification exist at all for extremely obvious atomic forms, or would that reintroduce the same ownership problem?
- If any deterministic intent path remains, can its boundary be stated as a small formal grammar rather than an expanding word list?

### Catalog parser boundary

- Can the same structured referent parser serve atomic, resource, device-set, and investigation requests?
- How should shorthand such as `48G`, `24G`, `8G`, `PoE+`, `SFP+`, family names, and model fragments be represented?
- Which catalog fields should be added to the current filter schema beyond brand/family/port_count/poe?
- When should a phrase be treated as an exact model identity versus a set of independent facets?

### Resolver behavior

- How are filters combined with explicit references?
- When does narrowing produce one safe result?
- What ambiguity threshold is acceptable?
- How should multiple physical devices sharing the same model/SKU be represented to the user?

### Product behavior

- Should queries that identify a set of devices be supported for non-device-set operations?

For example:

```text
48G'lerin alarmlarını göster
```

Possible product decisions:

1. support multi-device resource retrieval,
2. require clarification to one device,
3. declare that operation unsupported in v1.

This is a product capability decision and should not emerge accidentally from regex behavior.

---

# Regression Strategy After the Ownership Decision

Once the ownership boundary is accepted and implemented:

1. Run the existing Gold suite.
2. Run the existing Generated suite.
3. Run Legacy regression.
4. Do not change test expectations to match the implementation.
5. Do not immediately patch individual failures.
6. Classify each failure by missing capability/ownership.
7. Only modify production code when the fix expresses a general rule.

The objective is not merely to recover:

```text
40/40
16/16
56/56
```

The objective is to reach those scores with an architecture that still behaves sensibly on unseen language.

---

# Current Status

This document represents the **architecture direction to be reviewed**, not a final implementation declaration.

The project currently has working pieces for:

- catalog ingestion,
- structured facets,
- identity variants,
- resolver v5,
- ambiguity handling,
- UNKNOWN/null metadata behavior,
- deterministic atomic backend execution,
- fixed Level-1 investigation.

The remaining question in this stage is the clean ownership boundary between:

```text
natural-language intent understanding
```

and:

```text
deterministic catalog/reference understanding
```

The proposed answer is:

> **The planner decides what operation the user wants.  
> The catalog layer decides what the referenced network object means.  
> The resolver decides which concrete object(s) that reference identifies.  
> The backend decides what is true.**

This direction should be evaluated before the planner/resolver architecture is frozen and before moving to the next major phase: structured synthesis with evidence-reference grounding validation.
