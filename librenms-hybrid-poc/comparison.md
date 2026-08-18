# Hybrid PoC — comparison and recommendation

Generated from a live run of `hybrid_poc.py` against the local Ollama model
`librenms-qwen` (`think=false`, production parameters `temperature 0`,
`top_p 0.95`, `top_k 20`, `presence_penalty 1.5`), plus a variance sweep at
`temperature 0.7`.

Test set: 20 cases, 88 total run-instances per temperature
(14 atomic cases × 5 reps + 6 non-atomic cases × 3 reps).

## Headline results

| Metric | Path B (hybrid) | Path A (direct LLM) |
|--------|-----------------|---------------------|
| Overall, temperature 0.0 (production) | **88/88 (100%)** | 68/88 (77%) |
| Overall, temperature 0.7 (variance sweep) | **88/88 (100%)** | 63/88 (72%) |
| Atomic status subset, temp 0.0 | **70/70 (100%)** | 50/70 (71%) |
| Atomic status subset, temp 0.7 | **70/70 (100%)** | 48/70 (69%) |
| Status preserved (atomic), temp 0.0 | **70/70 (100%)** | 65/70 (93%) |
| Status preserved (atomic), temp 0.7 | **70/70 (100%)** | 61/70 (87%) |
| Entity resolved (atomic), temp 0.0 | **70/70 (100%)** | 55/70 (79%) |
| Entity resolved (atomic), temp 0.7 | **70/70 (100%)** | 56/70 (80%) |
| Mean latency (atomic, temp 0.0) | ~1.15 s | ~2.10 s (two LLM calls) |

The hybrid path never failed once in 176 run-instances across both
temperatures. The direct path failed 20/88 (23%) at the production temperature
and 25/88 (28%) in the variance sweep.

## Concrete failure modes of the direct path (Path A)

These are the T46 class, reproduced with the production system prompt. The
hybrid path handles every one of them deterministically.

1. **Status misreporting on formatting variation (the core T46 class).**
   Question `SW46 ayakta mı?` with tool result `{"hostname": "sw-46",
   "status": "up"}`. Path A answered, 5/5 times:

   > Hayır, mevcut verilerde SW46'nın durumu yok. Bu bilgi mevcut verilerde bulunmuyor.

   The model treated the user's `SW46` as a *different device* from the
   `sw-46` in the data and declared the data missing — even though the status
   field explicitly said `up`. This is exactly the fragile atomic-status
   behavior: the LLM is being asked to do a trivial normalization
   (`SW46` → `sw-46`) *and* a trivial status read, and it fails on the
   normalization. The deterministic resolver does this for free.

2. **Entity-resolution failure on unhyphenated/uppercase references.**
   For `sw47 çalışıyor mu?`, `sw48 çalışıyor mu?`, and `SW-47 çalışıyor mu?`,
   Path A's entity step returned `hostname: null` (5/5 each) — it could not map
   `sw47` → `sw-47`, `sw48` → `sw-48`, `SW-47` → `sw-47`. The deterministic
   resolver handles all of these.

3. **Ambiguity guessing (appears at higher temperature).** For
   `core switch çalışıyor mu?`, Path A guessed `core-sw-01` in 2/3 runs at
   temperature 0.7 (correct at 0.0). The deterministic resolver always returns
   the two candidates and asks for clarification — it never guesses.

4. **Fabrication / dangerous fuzzy match (appears at higher temperature).**
   For `depo switch çalışıyor mu?`, Path A's entity step returned
   `hostname: "sw-460"` in 1/3 runs at temperature 0.7 — silently selecting an
   unrelated device. The deterministic resolver returns no-match and never
   fabricates.

5. **Nondeterministic status failure (higher temperature).** For
   `sw460 çalışıyor mu?`, Path A replied "bu bilgi mevcut verilerde bulunmuyor"
   in 1/5 runs at temperature 0.7 despite correct `{sw-460, up}` data.

## Answers to the required questions

**1. Did the hybrid approach eliminate the original T46 failure?**
Yes. The exact `sw-46 çalışıyor mu?` wording happened to pass in both paths
(this model handles the canonical hyphenated lowercase form), but the hybrid
path makes the answer correct *by construction*: the atomic answer is emitted
by a deterministic formatter, so no LLM misread is possible.

**2. Did it also handle the T46 variations?**
Yes, 100% across all formatting variations (`Sw46`, `SW46`, `sw 46`, `SW-46`,
`sw-46'nın`). Notably, `SW46 ayakta mı?` is where the direct path failed 5/5 —
the variation that the hybrid path absorbs trivially.

**3. Did any entity-resolution edge case fail?**
No. `sw-46` vs `sw-460` stayed distinct, all case/hyphen/whitespace variations
resolved, `core switch` returned ambiguity (both candidates, no guess), and
`depo switch` returned no-match.

**4. Did investigation questions stay out of the atomic path?**
Yes. Both investigation cases were routed to `investigation` and never touched
the deterministic atomic formatter.

**5. Did historical questions stay out of the current-status path?**
Yes. Both past-tense cases were classified `unsupported` (never answered from
the current `status` field).

**6. Was the hybrid path more reliable than direct Qwen interpretation?**
Yes, by a wide margin: 100% vs 71–77% on the atomic subset, and 100% vs 72–77%
overall. The direct path's failures were reproducible (greedy decoding) on
specific phrasings and additional failures emerged at higher temperature
(guessing, fabrication). The hybrid path was also ~45% faster.

**7. Does the evidence justify implementing this architecture?**
Yes. The failure is a whole class, not one wording: the direct path failed on
casing/phrasing variations, unhyphenated references, ambiguity, and (at higher
temperature) fabricated devices. All of these are eliminated by moving
*entity normalization* and *atomic status interpretation* into deterministic
backend code, while leaving Qwen responsible for the part it is actually good
at (intent classification and, later, grounded synthesis for investigations).
The change is narrow — it only short-circuits the atomic-status path.

**8. Smallest next implementation step.**
Add the deterministic core behind the existing pipeline and gate the atomic
path on it:
1. A planner classification prompt (the few-shot prompt used here) returning
   `request_type` / `intent` / `device_query`.
2. A deterministic `resolve_device()` + status lookup + `format_atomic()` in the
   backend (read-only).
3. Route `atomic_fact + device_status` to the deterministic formatter; keep the
   investigation path exactly as it is (Qwen grounded synthesis).
4. Re-run the full 56-test suite plus these 20 variants to confirm 55/56 → 56/56
   with no investigation regressions.

## Caveats / limitations of this PoC

- The planner here used a specific few-shot classification prompt; that prompt
  is part of the proposed implementation, and planner robustness should be
  re-validated against the full suite and more varied inputs.
- Path A's entity step simulates production tool selection with the inventory
  shown in-context; real production may use a different tool-calling scheme,
  but the demonstrated failures (normalization, ambiguity, fabrication) are
  precisely the behaviors the deterministic resolver removes.
- Path A judging for atomic cases splits into two clean dimensions (hostname
  correctness and implied status). Judging for investigation/historical/
  ambiguity cases uses documented keyword heuristics; raw answers are preserved
  in `results.json` for inspection.
- The deterministic resolver intentionally does *not* do fuzzy matching; it
  only does exact-normalized and word-prefix matching, and returns ambiguity
  instead of guessing. This is a feature, not a limitation.

## Recommendation

**IMPLEMENT HYBRID** — the evidence shows a deterministic backend for atomic
device-status questions removes the entire T46 class of failures (100% vs
71–77% direct), is faster, and leaves the investigation path untouched.
