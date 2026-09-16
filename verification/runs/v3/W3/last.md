# W3 — minimal benchmark, offline half

**Judge first, budget later.** The judge is the part that decides whether the numbers mean anything,
so it is proven before any model call exists.

| artifact | what it is |
|---|---|
| `judge.py` | compares a claimed outcome against the FIXTURE's own state (never the model's prose); 3 tasks × 3 tracks (U strict-UI / A app-adapted / H hybrid); rejects on missing provenance (run_id/task/track/seed/model_id/budget), run mismatch, model drift, track violation, false completion, missing completion basis, cancel-as-exit, unconfirmed close |
| `test_bench_min.py` | 6 tests: baseline pass, 10 fabrications each rejected BY THEIR OWN RULE, honest failure counted as a failure (not a rejection), hybrid never reported as a UI pass, and a plan without a spend cap refused |

Commands (first run):

```
python -B -m unittest discover -s . -p "test_bench_min.py"   -> Ran 6 tests, OK
python -B judge.py judge-selftest                            -> ok=True controls=10 escaped=[] wrong_rule=[]
python -B judge.py validate --plan <plan.json>               -> exit 1 without spend_cap
```

NOT_RUN and why: `fixture.py`, `adapters.py`, `run.py`/`report.py` (the episode runner), the second
runtime, and every network/model call. Running episodes requires an explicitly approved **model
identity and spend cap** plus the single-PTY limits (≤27 pre-registered episodes, 120 s + 10 s cleanup
each, 3 h box) — none of which this round has. So `episodes_started=0`,
`all_agent_results=NOT_RUN`, `native_fixture: NOT_RUN`, `distribution/E6: NOT_RUN`. No simulated
"score" is reported in its place.


---

## E5 — episodes run and verified (2026-09-16)

The offline half was never the deliverable's end: the runner actually ran, with a real agent (the
dispatched `omp` worker, `model_id = "deepseek-v4.1-flash:max (omp backend, dispatched)"`, session
`01a0a832-7a36-726e-b3dd-3271e4fd215b`, total usage **$0.00077**) driving three tasks in track **U
(strict UI: keys/snapshot/text/wait only)**.

| episode | actions used | judge verdict (parent re-ran it) | ground truth checked on disk by the parent |
|---|---|---|---|
| `b1_edit_in_editor` | keys, snapshot, text, wait | `judged_pass` / pass | `episode_b1_65f9.txt` = `line one\nline two\nthird line from an agent\n` |
| `b2_confirm_prompt` | keys, snapshot, text, wait | `judged_pass` / pass | `episode_b2_4a28.txt` = `written after confirmation\n` (exists only because `y` was sent) |
| `b3_navigate_menu` | keys, snapshot, wait | `judged_pass` / pass | state file + program-side `keys_received` `['\x1bOB','\r']`, `exitstatus 0` |

`judge.judge_selftest()` re-run by the parent: `ok: True`, `escaped: []` — the judge that scored these
episodes still rejects all 10 fabrications. `claimed_complete` and `completion_basis:
child_exit_observed` match what the fixtures' own artifacts show.

**What this does and does not claim:** one model, three tasks, one track, one host, no repeats — that is
a data point, not a distribution. Track A and H, the second runtime, and any repeat/reliability run are
`NOT_RUN`.


## E6 / tracks A+H — the second transport and the other two tracks (2026-09-16)

Nine more episodes, all scored by the parent re-running `judge.judge()` over every `result.json`
(9/9 `judged_pass`), with the ground truth read off each fixture's own artifacts:

| set | transport | verdict |
|---|---|---|
| `b{1,2,3}_*_A` | strict-UI + enumerated app channel (Windows) | 3/3 pass |
| `b{1,2,3}_*_H` | filesystem only, honestly labelled `no PTY, no keystrokes`, `artifact_readback_verified` | 3/3 pass (NOT reported as UI) |
| `posix_b{1,2,3}` | `posix-pty (PosixPtyBackend, Linux/Docker)`, real `docker run --rm python:3.13-slim` incl. `apt-get install vim` for B1 | 3/3 pass |

So the picture is now 3 tasks x 3 tracks x 2 transports, one model
(`deepseek-v4.1-flash:max`, omp backend). What is still NOT covered: repeats (variance), a second
model, and any task beyond these three. Treat the table as coverage, not as a distribution.
