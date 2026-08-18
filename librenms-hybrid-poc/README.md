# LibreNMS hybrid-architecture PoC (T46 failure class)

Isolated proof-of-concept that tests whether a **planning → deterministic
backend** split eliminates the T46 class of failures: simple device-status
questions where the LLM occasionally misreads an explicit tool result such as

```json
{ "hostname": "sw-46", "status": "up" }
```

This is **not** a LibreNMS integration, **not** a change to the production
system, and **not** a rewrite of the main evaluation suite. It only simulates
the architectural boundary with mock device data.

## Directory contents

| File | Purpose |
|------|---------|
| `hybrid_poc.py` | The harness: Ollama planning, deterministic resolver/lookup/formatter, Path A vs Path B comparison, judging, results output. |
| `t46_variants.json` | The 20-case T46-family evaluation set (categories A–H). |
| `production_baseline_system.txt` | Read-only reproduction of the production `librenms-qwen` Modelfile SYSTEM prompt, used to make Path A faithful. |
| `results.json` | Full per-run, per-repetition, per-temperature results plus aggregated summaries (generated). |
| `comparison.md` | The evidence-based comparison and recommendation (generated). |
| `run_log.txt` | Console log of the last harness run. |

## Architecture under test

```text
User natural language
        |
        v
Qwen planning / intent understanding
        |
        +--> entity resolution when necessary
        |
        v
Approved backend tool
        |
        v
Deterministic operational fact
        |
        +--> Atomic fact question:  deterministic backend response
        |
        +--> Investigation question: return normalized tool results to Qwen
                                     for grounded synthesis
```

### Qwen responsibilities (Path B planner)
- Understand natural-language intent.
- Recognize device references (as raw `device_query`, **not** canonicalized).
- Decide `atomic_fact` vs `investigation` vs `clarification` vs `unsupported`.
- Emit the planning schema:

```json
{
  "request_type": "atomic_fact | investigation | clarification | unsupported",
  "intent": "device_status | investigation | unknown",
  "device_query": "raw user reference or null"
}
```

### Backend responsibilities (deterministic, no LLM)
- Resolve canonical device identities (case/hyphen/whitespace-insensitive).
- Validate arguments, enforce read-only, retrieve status.
- Preserve `up` / `down` / `unknown` exactly.
- Produce the final deterministic atomic answer.

## Entity resolution (deterministic)

`normalize()` lowercases, strips a trailing possessive clitic, and removes
whitespace/hyphens/underscores, so these all resolve to `sw-46`:

```text
sw-46   SW-46   Sw46   sw46   sw 46   SW 46
```

Matching is exact-on-normalized-form first, then a word-prefix candidate match
for semantic references (e.g. `core switch`). It never uses dangerous fuzzy
matching and never guesses:

- `core switch` → **ambiguous** (`core-sw-01`, `core-sw-02`)
- `depo switch` → **no match**
- `sw46` vs `sw460` → distinct (`sw-46` vs `sw-460`)

## Path comparison

- **Path B (hybrid):** Qwen plans → deterministic resolve → deterministic
  lookup → deterministic formatter. The LLM is *not* required to reinterpret
  `status: up`.
- **Path A (direct):** current production baseline. The LLM resolves the device
  and then, using the production system prompt, reads the tool-result JSON and
  writes the final answer itself.

## Run it

```bash
# default: temperature 0 (production) + 0.7 variance sweep
python3 hybrid_poc.py --model librenms-qwen --temps 0.0,0.7

# single temperature, override repetition count
python3 hybrid_poc.py --model librenms-qwen --temps 0.0 --reps 5
```

Options: `--model`, `--temps`, `--reps`, `--think` (default off), `--cases`,
`--out`.

Inference always runs with `think=false` (thinking disabled), matching the
production configuration (`temperature 0`, `top_p 0.95`, `top_k 20`,
`presence_penalty 1.5`).

## Notes / limitations

- The atomic deterministic answer is Turkish and preserves state:
  - `up` → `"sw-46 şu anda çalışıyor."`
  - `down` → `"sw-47 şu anda çalışmıyor."`
  - `unknown` → `"sw-48 durumu bilinmiyor."` (never coerced to up/down)
- Path A judgement for atomic cases is split into two independent dimensions:
  (1) did the LLM resolve the correct hostname, and (2) did its final answer
  imply the correct status. Both are reported in `results.json`.
- Investigation / historical / ambiguity judgement in Path A uses documented
  keyword heuristics because "correct" is qualitative there; raw answers are
  always stored in `results.json` for inspection.


## Hybrid PoC v2 — inventory-aware, typo-tolerant resolution

v2 moves entity resolution fully into the deterministic backend. The planner
only classifies intent and extracts a raw device reference; the backend
resolver decides resolved / ambiguous / no_match and logs a reason.

### Inventory (inventory.json)
- models: the 8 real HP ProCurve models from
  device_controller_brand_model_only.xlsx, stored verbatim (brand, sku,
  model, canonical_name, search_text, aliases, source_occurrences).
- devices: the 6 baseline hostnames (sw-* -> J9772A 2530-48G-PoEP,
  core-sw-* -> J4850A 5304XL) plus 5 synthetic fixtures covering J9775A,
  J9776A, J9780A, J9783A and JL357A.

### Resolver (resolver.py)
Layer order (highest confidence first):
1. exact hostname (case-insensitive literal)
2. normalized hostname (case/space/hyphen/underscore/clitic)
3. alias (device-level, e.g. core1 -> core-sw-01)
4. typo (Damerau-Levenshtein distance <= 1 + QWERTY adjacency +
   numeric-suffix preservation + known-prefix awareness)
5. metadata (brand/sku/model/canonical_name/search_text)
6. ambiguous / no_match

Reasons logged: exact | normalized | alias | typo | metadata | ambiguous | no_match.

Auto-resolve rule: a typo resolves only when exactly ONE candidate is at the
minimum edit distance (keyboard/prefix/suffix tie-breakers). Ties return
ambiguous. sw466 -> ambiguous {sw-46, sw-460}; sq46 / se46 / sww46 -> sw-46.

Device-set: resolve_device_set() filters by model/SKU/brand/description and
returns every match (never picks one). J9772A -> {J9772A};
2530 48G -> {J9775A, J9772A}; 48 port PoE ProCurve -> {J9772A, JL357A}.

### Run
    python3 test_resolver.py     # offline unit tests (no LLM)
    python3 hybrid_poc.py --model librenms-qwen --cases t46_v2_cases.json --temps 0.0,0.7 --out results_v2.json

### Results
See comparison_v2.md and results_v2.json.
