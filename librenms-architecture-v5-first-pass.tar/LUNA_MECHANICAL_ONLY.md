# Luna task after architecture files are supplied

Do not design or rewrite the architecture.
Do not add regexes, SKU literals, tests, fixtures, expected outputs, or prompt workarounds.

Perform only these mechanical steps:

```bash
cd <repo-root>
bash <bundle-path>/install_v5.sh "$PWD"
git diff --check
git status --short
git diff -- hybrid-gold-v3/resolver_candidate_v4.py
```

The last command must be empty.

Then run the existing regression suites unchanged, using
`hybrid-gold-v3/resolver_candidate_v5.py` as the active resolver for the v5 run.
Preserve the raw outputs and report every failure without patching it.

If tests pass, show the diff and commit exactly the supplied architecture change.
Do not make additional code changes unless explicitly instructed afterward.
