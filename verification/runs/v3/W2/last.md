# W2 — credible evidence, offline

Deliverable: an offline reviewer that REJECTS bundles claiming more than their own fields support.
`verify_evidence.py` (8 rule groups), `credible_fixtures.py` (1 honest bundle + 16 single-lie
variants), `test_credible_evidence.py` (8 tests), `MANIFEST.json`.

Command and result (first run):

```
python -B -m unittest discover -s . -p "test_*.py"     -> Ran 8 tests, OK
verify_evidence.reject_controls(good, negative_cases()) -> ok=True, controls=16, escaped=[]
```

Every falsification is rejected **by the rule it targets** (no accidental rejections): metadata hash,
empty manifest, absolute and `..` path escape, missing evidence ref, empty selected text,
hash/length contradiction, `written` with a short payload, `budget_limited` claimed complete, adapter
basis named runtime, hidden provenance conflict, cancel-acked claimed as an exit, `closed_confirmed`
without an observation, replay with gaps, a claim exceeding its evidence level, and a ConPTY bundle
claiming wire exactness.

Boundaries: the verifier treats the bundle as DATA (nothing is imported, executed, fetched or opened
from it), enforces size/depth/item limits, and never resolves a provenance conflict on the reader's
behalf. What it does NOT do this round: the `conformance.py` profile extension and
`test_conformance_contract.py` (old-CLI compatibility for the kit runner) — not implemented, so
`new_credible_native_profile: NOT_RUN`, `macos: NOT_RUN`, `product_release: NOT_RUN`.
