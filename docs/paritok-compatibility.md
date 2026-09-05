# PariTok compatibility contract

ContextOps treats PariTok as an external treatment, not as an unversioned implementation detail.
The default live installation is PariTok 1.3.11. Historical Wave A evidence remains attributed to
1.3.3 and is never rewritten as evidence from a newer dependency.

## Tested matrix

| PariTok | Role | Cache-risk expectation | Required result |
|---|---|---|---|
| 1.3.3 | Historical evidence reproduction | Content-only cross-query reuse is observable | Disabled and query-aware isolation pass |
| 1.3.11 | Current default runtime | Content-only cross-query reuse is observable | Disabled and query-aware isolation pass |

The authoritative machine-readable matrix is
[`configs/paritok-compatibility.json`](../configs/paritok-compatibility.json). CI installs each
version independently and runs the compatibility audit, provider-free regression, safe-proxy
contract tests, and the full test suite.

```bash
python -m pip install -e '.[dev,live]'
contextops-lab compatibility-audit
contextops-lab provider-free-regression --engine deterministic
pytest -q
```

`compatibility-audit` fails closed when the installed version is not in the matrix or when observed
cache behavior differs from the versioned expectation. Adding a new version requires a matrix row
and a green CI lane; changing the default dependency alone is insufficient.

## Evidence boundary

Compatibility means the ContextOps cache-isolation and exact-original fallback contracts still
behave as tested. It does not transfer provider-backed quality, latency, or cost evidence from one
PariTok version to another. A new default version must complete the provider-free gates before a
bounded recovery pilot is considered.
