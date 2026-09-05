# 0.8.0 release checklist

Candidate branch: `codex/p0-paritok-compatibility`

## Code and dependency

- [x] Package version is 0.8.0.
- [x] Default live dependency is pinned to PariTok 1.3.11.
- [x] PariTok 1.3.3 remains an explicit historical compatibility lane.
- [x] Unsupported versions and cache-contract drift fail the compatibility audit.
- [x] Multi-turn execution fails closed for an unverified cache contract.
- [x] Validator rejection forwards the exact original context.

## Verification

- [x] Standard-library test suite passes without the optional live dependency.
- [x] Ruff and Python bytecode compilation pass.
- [x] PariTok 1.3.11 source compatibility audit passes without a provider call.
- [x] Deterministic provider-free regression passes all cache, guard, and recovery gates.
- [ ] GitHub CI passes both packaged dependency lanes: 1.3.3 and 1.3.11.
- [ ] Real local PariTok 4B/Ollama provider-free regression passes on release infrastructure.
- [x] Safe-proxy HTTP boundary test passes with the complete `paritok[proxy]` dependency set.

## Evidence and documentation

- [x] Historical Wave A evidence remains attributed to PariTok 1.3.3.
- [x] The compatibility contract states that evidence does not transfer across versions.
- [x] Architecture, one-minute demo, runbook, and changelog are present.
- [x] Provider-backed recovery, semantic non-inferiority, and production claims remain explicitly
  unproven.
- [ ] A bounded provider-backed recovery run is authorized and completed, if it is included in the
  release claim.

## External release actions

- [ ] Push the candidate branch.
- [ ] Open or update the pull request and obtain review.
- [ ] Merge only after required CI checks are green.
- [ ] Tag `v0.8.0` and publish release notes.

Unchecked external actions are intentionally not performed by local implementation work.
