# EMR-43 architecture v5 first pass

This bundle contains the architecture code itself. Luna does not need to design it.

Implemented in this pass:

1. controlled catalog ingest and facet extraction
2. UNKNOWN facet preservation and ingest reporting
3. catalog-driven weighted identity variants
4. deterministic-first device-set planning
5. schema-constrained LLM fallback contract
6. structured device-set resolver filtering
7. frozen v4 compatibility for already-tested single-device resolution

Intentionally not included yet:

- synthesis refactor
- grounding validator
- new test design
- fixture or expected-output changes

## Apply

From the repository root:

```bash
bash <bundle-dir>/install_v5.sh "$PWD"
```

The installer refuses to run unless both frozen source hashes match the known
baseline. It also verifies that `resolver_candidate_v4.py` remains unchanged.

After apply, run the existing suites unchanged with
`hybrid-gold-v3/resolver_candidate_v5.py` as the active resolver.
