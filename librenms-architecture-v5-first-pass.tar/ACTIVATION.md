# Activation after adding the files

Use the new resolver explicitly for the next product-development run:

```bash
export SUT_PLANNER_SCHEMA=gold
# run_gold.py / your runner should receive:
# --resolver hybrid-gold-v3/resolver_candidate_v5.py
```

Do not overwrite or rename `resolver_candidate_v4.py`.

Do not edit Gold, Generated, Legacy, holdout query, fixture, or expected-result files.
The exposed Hidden-v1 queries are no longer a clean holdout for tuning. Any new
independent hidden evaluation must use a new unseen suite.
