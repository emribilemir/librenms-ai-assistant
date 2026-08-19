# EMR-43 Adversarial Targeted v1 Run Report

## Integrity

- Locked package files were read from `/Users/emirbilici/Downloads/emr43-adversarial-targeted-v1/` and were not edited.
- No case IDs or exact case strings were added to production code.
- No Gold/Generated expected results, fixtures, SpyBackend, planner taxonomy, or runners were edited.
- `librenms-qwen` was used as the system under test only. No local semantic score was assigned to synthesis outputs.
- The accepted resolver was `hybrid-gold-v3/resolver_candidate_v4.py`; EMR-43 semantic synthesis output remains for external GPT-5.6 Sol judgment.

## PRE-PATCH results

- Resolver: 13/28
- Synthesis coverage/input contract: 0/12
- E2E: 9/18 deterministic

Raw PRE-PATCH results:

- [prepatch_resolver.json](prepatch_resolver.json)
- [prepatch_synthesis.json](prepatch_synthesis.json)
- [prepatch_e2e.json](prepatch_e2e.json)

## Patch scope

1. Added conservative fuzzy catalog identity for structured SKU references with one omitted leading character or one edit, while rejecting short numeric fragments and preserving ambiguity.
2. Added general device-set facets for brand, port count, positive PoE, explicit negative PoE, and numeric model-family constraints.
3. Added synthesis coverage metadata with `retrieved_sources` and `not_retrieved_sources` over `device`, `ports`, `alerts`, and `events`, preserving `_synthesize(query, evidence, model, synthesis_system)`.

## POST-PATCH results

- EMR-43 resolver: 28/28
- EMR-43 synthesis mechanical coverage contract: 12/12
- EMR-43 E2E deterministic: 18/18
- Gold regression: 40/40
- Generated regression: 16/16
- Legacy regression: 55/56; one deterministic failure remains in the unchanged legacy suite. Semantic judge was skipped.

Raw POST-PATCH results:

- [postpatch_resolver.json](postpatch_resolver.json)
- [postpatch_synthesis.json](postpatch_synthesis.json)
- [postpatch_e2e.json](postpatch_e2e.json)
- [postpatch_gold.json](postpatch_gold.json)
- [postpatch_generated.json](postpatch_generated.json)
- [postpatch_legacy.json](postpatch_legacy.json)

The intermediate post-patch run before the existing Gold compatibility adjustment is preserved under `postpatch_before_gold_regression_fix_*.json`.

## Evidence

- [PRE Git/runtime evidence](../emr43-evidence/pre/)
- [POST Git/runtime evidence](../emr43-evidence/post/)
- [Source diff](emr43_source_diff.patch)

Frozen HEAD stayed unchanged. The implementation hash differences between PRE and POST are limited to the two intended product files: `librenms-hybrid-poc/hybrid_poc.py` and `hybrid-gold-v3/resolver_candidate_v4.py`. Python execution also refreshed tracked `__pycache__` bytecode artifacts; the returned source diff excludes those generated files.
