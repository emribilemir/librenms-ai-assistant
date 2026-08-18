# Hybrid PoC v2 — comparison

Generated from results_v2.json (model=librenms-qwen, think=False).

## Headline results

| temperature | Path B (hybrid) | Path A (direct) |
|---|---|---|
| 0.0 | 132/132 (100%) | 94/132 (71%) |
| 0.7 | 132/132 (100%) | 81/132 (61%) |

## Resolution reasons (Path B, temperature 0.0)

| reason/route | count |
|---|---|
| exact | 35 |
| normalized | 35 |
| typo | 15 |
| ambiguous | 12 |
| no_match | 9 |
| metadata | 9 |
| investigation | 6 |
| unsupported | 6 |
| alias | 5 |

## New typo/metadata cases (temperature 0.0)

| id | question | expected route | Path B | reason |
|---|---|---|---|---|
| V2-typo-sq46 | sq46 çalışıyor mu? | atomic | PASS | typo |
| V2-typo-sww46 | sww46 çalışıyor mu? | atomic | PASS | typo |
| V2-typo-se46 | se46 çalışıyor mu? | atomic | PASS | typo |
| V2-typo-sw466 | sw466 çalışıyor mu? | clarification | PASS | ambiguous |
| V2-prefix-sw4 | sw4 çalışıyor mu? | clarification | PASS | ambiguous |
| V2-prefix-core | core çalışıyor mu? | clarification | PASS | ambiguous |
| V2-set-J9772A | J9772A çalışıyor mu? | device_set | PASS | metadata |
| V2-set-2530-48G | 2530 48G çalışıyor mu? | device_set | PASS | metadata |
| V2-set-48-port-PoE-ProCurve | 48 port PoE ProCurve çalışıyor mu? | device_set | PASS | metadata |
| V2-alias-core1 | core1 çalışıyor mu? | atomic | PASS | alias |
| V2-unknown-xyz999 | xyz-999 çalışıyor mu? | clarification | PASS | no_match |
| V2-unknown-firewall | firewall-01 çalışıyor mu? | clarification | PASS | no_match |

## New-case Path B pass rate

| temperature | new cases passed |
|---|---|
| 0.0 | 44/44 |
| 0.7 | 44/44 |
