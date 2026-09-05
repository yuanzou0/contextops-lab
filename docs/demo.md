# One-minute release-candidate demo

This demo exercises the release gates without making a provider request. Use a fresh environment
with the live extra already installed.

```bash
python -m pip install -e '.[dev,live]'

# 1. Verify the installed dependency is explicitly supported.
contextops-lab compatibility-audit --output /tmp/paritok-compatibility.json

# 2. Reproduce the cross-intent cache risk and its two isolation controls.
contextops-lab cache-contract-audit --output /tmp/cache-contract-audit.json

# 3. Exercise cache, critical-signal, and exact-original fallback contracts.
contextops-lab provider-free-regression \
  --engine deterministic \
  --output /tmp/provider-free-regression.json \
  --report /tmp/provider-free-regression.md

# 4. Run the complete release-candidate suite.
pytest -q
```

Expected signals:

- `Compatibility passed: true`;
- `Content-only query reuse observed: true`;
- `Isolation interventions passed: true`;
- provider requests and provider cost remain zero; and
- the complete test suite passes.

The observed content-only reuse is a reproduced risk, not a desired success condition. The demo
passes because ContextOps detects it and verifies that both supported isolation strategies prevent
cross-intent reuse. A real 4B/Ollama run is a separate release-host check:

```bash
contextops-lab provider-free-regression --engine local_paritok_4b \
  --output /tmp/provider-free-local-4b.json \
  --report /tmp/provider-free-local-4b.md
```
