# HANDOFF — the next update

Written 2026-09-16, after 0.3.2 shipped. Read this with `verification/README.md` (what the evidence
is) and `THINK/mandate.md` in `~/.omp/extra-hands/` (what the Owner asked for, per item).

## Where the product stands

| item | value |
| --- | --- |
| `main` | `1bcc526` (merge of the test-only issue-#15 delta); released state `e7877c2` = tag `v0.3.2` |
| releases | 0.3.0, 0.3.1, 0.3.2 on PyPI + GitHub Releases; every wheel verified byte-for-byte against its tag |
| CI | Lint, CI, CodeQL, Docker, Release Drafter, Publish to PyPI — green on the release commit |
| local gates | `python tests/run_all.py` → 56/56; `ruff check --select E9,F63,F7,F82 .` clean; **`mypy --platform linux`** clean (on Windows the POSIX stubs hide real errors — always pass `--platform linux`) |
| this machine | `smartcli-toolkit 0.3.2` installed; any harness pinning an older runtime must be restarted (see the Codex incident below) |

## Open items, in the order I would take them

1. **Repeats / variance.** Every cell of the E5/E6 table is a single run. Nothing here can say whether a
   pass is stable. Three repeats of the nine episodes (`runs/v3/W3/episodes*`) would turn coverage into
   a distribution. Cheapest real work available.
2. **A second model.** Same nine episodes, a different model id, same judge — that is what makes the
   numbers comparative rather than anecdotal. The judge already rejects a `model_id` that drifts from
   the plan.
3. **W2 conformance profile.** Extend the kit's `tools/conformance.py` with an explicit profile and
   basis origin, plus a contract test for the old CLI shape. The offline verifier beside it
   (`runs/v3/W2/verify_evidence.py`, 16 single-lie fixtures) is done.
4. **More tasks.** B1–B3 are three tasks; a capability claim needs more.
5. **A05/A06 tail.** The merged fix bounds the reply stall (2 s window, 60 s ceiling) and makes the
   reader cap an admission limit; what is *not* proven is behaviour under a genuinely hostile peer.
6. **The Codex incident, if it recurs.** `list_sessions` timed out at 15 s while the underlying command
   measures 0.10 s; the cause was a pre-0.3.2 runtime plus a single-worker MCP server. If it happens
   again, capture what tool call preceded the stall — that is the missing evidence, not more guessing.

## Getting back in

```powershell
# 1. the product
cd D:\Project\SmartCLI
python tests/run_all.py                 # expect 56/56, ~2.5 min
ruff check --select E9,F63,F7,F82 . ; mypy --platform linux

# 2. the evidence tree
cd D:\Project\SmartCLI\verification
python -B runs\v3\W3\judge.py judge-selftest          # expect ok:true, escaped:[]
python -B runs\v3\W2\verify_evidence.py review --bundle <bundle.json>

# 3. dispatch (Owner's word; the omp backend is the cheap lane)
powershell -NoProfile -ExecutionPolicy Bypass -File `
  "$env:USERPROFILE\.codex\skills\codex-dispatch\scripts\dispatch.ps1" `
  -Backend omp -Cwd <tree> -PromptFile <brief.md> -OutFile <last.md> -TimeoutSec 3600
```

Worker briefs that already exist and are known to work:
`~/.omp/extra-hands/PROMPTS/smartcli-worker-briefs/{A-issue15,B-episodes,C-liveness,D-bench-runner}.md`,
plus the follow-ups under `%TEMP%\codex-dispatch\<id>\` while that temp survives.

## The two discipline rules this round earned the hard way

1. **A verification artefact needs the same scrutiny as the code.** Issue #15 was filed on a probe that
   assumed a lossless 262 144-byte burst on a transport that drops bursts; when it was measured with raw
   `winpty` (no SmartCLI at all) the premise collapsed. Measure what the harness can physically deliver
   before declaring a product defect.
2. **A release is not delivered until the machine runs it.** The repo, the tag and PyPI said 0.3.2 while
   the installed copy was 0.3.0 and a harness was live on 0.2.3 in memory — that is what the Owner saw
   as "Codex broke". Install the release and restart anything pinning the old runtime as the last step
   of every release.
