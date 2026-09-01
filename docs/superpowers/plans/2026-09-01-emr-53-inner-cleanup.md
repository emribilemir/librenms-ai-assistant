# EMR-53 Repository Cleanup Implementation Plan

> Linear source: [EMR-53](https://linear.app/emribilemir/issue/EMR-53/main-sonrasi-repo-cleanup-ve-branchworktree-hijyenini-tamamla)

**Goal:** Remove tracked generated artifacts, give tests and fixtures stable homes, preserve the active PoC runtime contract, and finish the public documentation without inflating the main README.

**Architecture:** Keep the active PoC entry points and the `hybrid-gold-v3` acceptance bundle at their current public paths. Move only root-level tests into `tests/` and reusable input data into `fixtures/`; update path resolution to derive the PoC root explicitly. Delete reproducible result/log/comparison snapshots and ignore their future outputs.

**Tech Stack:** Python standard library, `unittest`, Git, Markdown, JSON.

---

### Task 1: Establish a clean, isolated baseline

**Files:**
- Verify: repository status, branch and worktree inventory
- Test: `librenms-hybrid-poc/test_*.py`

1. Confirm `main` matches `origin/main` and the source worktree is clean.
2. Create `codex/emr-53-inner-cleanup` in an isolated worktree.
3. Run the complete offline test suite and record any environment-only failures.

### Task 2: Separate tests and fixtures without changing runtime behavior

**Files:**
- Move: `librenms-hybrid-poc/test_*.py` to `librenms-hybrid-poc/tests/`
- Move: `inventory.json`, `t46_variants.json`, `t46_v2_cases.json`, `emr52_acceptance_queries.json`, `production_baseline_system.txt` to `librenms-hybrid-poc/fixtures/`
- Modify: `librenms-hybrid-poc/hybrid_poc.py`
- Modify: `librenms-hybrid-poc/resolver.py`
- Modify: moved tests with repository-relative path assumptions

1. Move tests and fixture inputs into dedicated directories.
2. Update default fixture paths and test import/path setup.
3. Run the full offline suite from the repository root.

### Task 3: Remove reproducible generated artifacts

**Files:**
- Delete: root `comparison*.md`, `results*.json`, `run_log*.txt`, `make_comparison.py`
- Delete: generated result/summary/failure and external-judge output files under `hybrid-gold-v3/`
- Modify: `.gitignore`
- Modify: `librenms-hybrid-poc/hybrid-gold-v3/ARTIFACT_MANIFEST.json`

1. Verify each candidate is an output or historical snapshot rather than a runtime input.
2. Delete the tracked outputs while retaining source cases and fixtures.
3. Add narrowly scoped ignore rules for future local evaluation output.
4. Update the artifact manifest so it describes only tracked source assets.

### Task 4: Refresh documentation

**Files:**
- Modify: `README.md`
- Modify: `librenms-hybrid-poc/README.md`
- Modify: `librenms-hybrid-poc/hybrid-gold-v3/README.md`

1. Document the new tests/fixtures layout and current test count.
2. Keep Debian/macOS/SNMPSim operational setup in the optional installation guide.
3. Add the next-direction sequence: LibreNMS native chat integration, then latency optimization.
4. Remove documentation that presents deleted snapshots as tracked artifacts.

### Task 5: Verify and publish the cleanup branch

**Files:**
- Verify: all changed files

1. Run JSON validation and Python compilation.
2. Run all 90 offline tests with localhost permission and the resolver self-test.
3. Check tracked artifacts, ignored outputs, clean status, and branch diff.
4. Commit with an EMR-53-scoped message and push the branch to GitHub.
5. Report the branch, commit, verification evidence, and whether a PR/main merge remains.
