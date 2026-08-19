# Architecture v5 First-Pass Rebase Report

## Frozen baseline

- Branch: `main`
- HEAD: `99cb6670176897ebf04f5ecb8fdd457caa49aec7`
- Frozen v4 SHA: `f925a75fe86d2b3a99040b4b608c93effc782cac9f60848d339c5a2fb62ba6f4`
- Frozen v4 verification: matched exactly
- Initial working tree: not clean; prior holdout/EMR-43 artifacts and source changes existed

The supplied `.tar` path is a directory, not an archive. The old installer was not run, as instructed. The bundle files were inspected directly.

## Dirty v4 analysis

The preserved `/tmp/current-v4-vs-head.patch` contains only the later EMR-43 experimental resolver changes: fuzzy SKU identity, resolver-side PoE/port-count parsing, Turkish terms such as `olmayan`, `poe'siz`, and `tane port`, bare-number guards, and device-set natural-language filtering. It was superseded by the v5 architecture and v4 was restored to frozen HEAD. The patch remains at `/tmp/current-v4-vs-head.patch`.

## Applied v5 files

Created from the supplied bundle without modification:

- `hybrid-gold-v3/catalog_ingest.py`
- `hybrid-gold-v3/resolver_candidate_v5.py`
- `librenms-hybrid-poc/planner_v2.py`

Modified:

- `librenms-hybrid-poc/hybrid_poc.py`

The existing synthesis-only EMR-43 working-tree delta was preserved. The prepared v5 delta adds planner/catalog/filter integration only. Active v5 test runs used `hybrid-gold-v3/resolver_candidate_v5.py`; v4 remains frozen compatibility history.

## Architecture inspection

- Catalog ingest owns model-string parsing, normalized facets, identity variants, and ingest reporting.
- Planner v2 owns deterministic-first natural-language device-set constraint extraction and tri-state filters.
- Resolver v5 consumes structured filters and catalog-derived variants; it does not add the dirty v4 natural-language parser.
- Ambiguous shortened identities remain ambiguous.
- UNKNOWN/null facet values remain observable through `unevaluated_*` fields and ingest reports.
- Frozen v4 compatibility is retained through the v5 sibling import.
- Investigation and synthesis behavior was not changed by the supplied v5 delta.

## Smoke inspection

Observed with v5:

- 48-port + PoE + ProCurve → `J9772A`, `JL357A`
- 48-port non-PoE → `J9775A`
- family `2530` → catalog-derived 2530 models
- `9772A` → ambiguous across two devices
- `9772` → ambiguous across two devices
- unknown chassis port count → partial ingest with `port_count` and `poe` unknown; filtering reports the row as unevaluated

## Test results

| Suite | Passed | Failed | Total | Failure class |
|---|---:|---:|---:|---|
| Gold | 35 | 5 | 40 | planner / structured filtering / compatibility regression |
| Generated | 14 | 2 | 16 | planner / structured filtering |
| Legacy | 55 | 1 | 56 | unrelated existing failure |

Gold failures: `GOLD-012`, `GOLD-017`, `GOLD-019`, `GOLD-020`, `GOLD-030`.

Generated failures: `GEN-007`, `GEN-011`.

The direct retrieval failures route `portlarını göster`, `eventlerini göster`, `alarmını göster`, and `loglarını göster` to `device_set`; these are planner ownership regressions. The `2530 48G` failures return only `J9775A` instead of the established `J9772A` + `J9775A` set; this is structured-filter/reference compatibility behavior. The Legacy failure is the existing `T46` case.

Raw results:

- [Gold results](gold_results.json)
- [Generated results](generated_results.json)
- [Legacy results](legacy_results.json)
- [Gold log](gold.log)
- [Generated log](generated.log)
- [Legacy log](legacy.log)

## Recommendation

DO_NOT_COMMIT

The prepared v5 implementation introduces hard Gold/Generated regressions. Per instructions, no post-test patch was applied.
