# hybrid-gold-v3 self-test

This is a harness/reference-adapter self-test only. It is not the real local Qwen/SUT acceptance result.

## Source provenance correction

The uploaded Excel contains only `Brand` and `Model`. It does not contain production hostnames or operational state. v3 therefore uses real source-backed SKU/model identities in user-facing Gold queries and uses explicit `lab-<sku>-NN` names only for synthetic fixture instances.

## Results

- Gold deterministic harness self-test: **40/40**
- Generated wording robustness self-test: **16/16**
- Local semantic judge used: **No**
- Gold external semantic cases pending: **7**
- Generated external semantic cases pending: **3**

## Central proof pair

`J9774A up mı?`

Expected path: exact catalog identity -> one lab fixture -> `get_device` -> deterministic answer -> no LLM.

`J9774A up gözüküyor ama ben tepki alamıyorum.`

Expected path: same identity -> `get_device + get_ports + get_alerts + get_events` -> LLM investigation. Fixture status is up while port 8 is admin-up/oper-down with matching alert/events.

## Resolver note

The v3 suite exposed one additional set-resolution edge case: literal model `2530-8-PoEP` must not also absorb sibling `2530-8G-PoEP`, while broad phrase `2530 48G` must still return both J9772A and J9775A. `resolver_candidate_v4.py` implements literal-exact precedence on device-set queries before broader token filtering.
