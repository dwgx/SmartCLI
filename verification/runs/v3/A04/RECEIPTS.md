# A04 receipts — S1, S2, S2p, S3, S4, S5 + N1 (2026-09-16)

Owner authorization: approved this round ("全力发挥去做吧…全部做完收尾就push 打tag"). Base: HEAD
`701e61f` + the T05/T04/T03 overlay. Kit `D:\Project\SmartCLI-v2-handoff`, RUN `D:\Project\SmartCLI-v3-runs`.

## Slices, files, and what each proved

| slice | files (physical) | first result | mutation (isolated copy) |
|---|---|---|---|
| **S1** budgeted transport + io accounting | `pty_backend.py`, `session.py` (+2 twins), `tests/test_a04_read_budget.py`, `run_all.py` = 6 | `Ran 17 tests, OK` | `a04-s1-ignore-budget` → 1 FAIL; `-drained-when-full` → 2 FAIL; `-silent-fallback` → 1 FAIL; restored → OK |
| **S2** STABLE requires drained | `readiness.py` (+twin), `session.py` (+twin), `tests/test_a04_pending_readiness.py`, `run_all.py` = 6 | `Ran 10 tests, OK` | `a04-s2-no-gate` → 3 FAIL |
| **S2p** mid-sequence visibility | `screen_model.py` (+twin), `session.py` (+twin), `tests/test_a04_parser_pending.py`, `run_all.py` = 6 | `Ran 8 tests, OK` | covered by S2p's own `None`-not-`False` case (decoder removed) |
| **S3** daemon service turns + io surface | `tui.py`, `mcp_server.py`, `session.py` (+twin), `tests/test_a04_daemon_service.py`, `tests/test_a04_io_surface.py`, `run_all.py` = 7 | `Ran 6 + 4 tests, OK` | **N1 case B** (service removed from a copy) → the fixture stalls at 12 288 B, CPR unanswered |
| **S4** close protocol | `pty_backend.py`, `session.py` (+2 twins), `tui.py`, `tests/test_a04_close_state.py`, `run_all.py` = 7 | `Ran 7 tests, OK` | `a04-s4-always-confirmed` → 2 FAIL |
| **S5** Windows payload cap | `pty_backend.py` (+twin), `tests/test_a04_winpty_backlog.py`, `run_all.py` = 4 | `Ran 5 tests, OK` | `a04-s5-no-backpressure` → 1 FAIL |

Two deviations, both reported rather than hidden:

* **DEVIATION-1 (S2p, 4 → 6 files).** `session.py` had to adopt the model-level
  `stream_incomplete()` in the same slice; the alternative was two competing definitions of the same
  truth (`None` vs filter-only), which the design forbids. Files: model+twin, session+twin, test,
  `run_all.py`.
* **DEVIATION-2 (S3, 5 → 7 files).** The long-wait path reads through `PtySession.wait_*`, whose
  `read_fn` lives in `session.py`; without that file the "long wait must use the same budget" clause
  cannot be met. Files: `tui.py`, `mcp_server.py`, session+twin, two tests, `run_all.py`.

## N1 — candidate service and close, on real transports

`N1/n1_daemon_idle.py` starts the REAL daemon and never calls pump/snapshot until its first request;
the verdict is the child's own report.

| case | platform | CPR answered while idle | produced before first contact | fixture completed with no client pump |
|---|---|---|---|---|
| A shipped daemon | POSIX (container, real `pty.fork`) | **0.169 s** | 61 440 B | **yes**, 262 144 B |
| B service turns removed (copy) | POSIX | not until the client asked (2.75 s) | **0 B** | **no**, stalled at 12 288 B |
| C shipped daemon | Windows (real ConPTY) | **0.164 s** | 131 072 B | **yes**, 131 072 B |
| C-x after S4/S5 | Windows | 0.164 s | 131 072 B | yes |

Artifacts: `N1/case-A*.json`, `case-B-no-service.json`, `case-C*.json`.
The Windows child requests raw VT input mode before asking, otherwise the console's line editor
swallows the reply and the fixture would report "not answered" for its own reason.

## What the slice set actually closes, and what it does not

* Closed: idle starvation (measured before: child stalled at 12 288 B, CPR never answered), request
  starvation (service runs per iteration, bounded), unbounded Windows backlog (cap on accounted
  payload: queue + chunk in hand + held suffix), "stable while unread" (STABLE now requires
  `local_cut == drained` and no pending facts), mid-sequence blindness (`stream_incomplete`),
  close honesty (`closed_confirmed` vs `close_unconfirmed` with last progress), and the io evidence
  reaching CLI/MCP with `basis_origin=runtime`.
* **Not closed:** S6 (device-reply progress; a partial reply is still best-effort and its failure is
  not yet surfaced), A05 (`tui.py`'s "64" is a filter, not an admission cap), A06 (`_reply` can still
  stall the single worker for `POST_AUTH_TIMEOUT = 60 s`; `jobs`/`readers` remain unbounded).
  N2, W2, W3 and E6 are NOT_RUN in this round.
* Windows remains `source_wire_exact=false`: ConPTY composes the stream (X2 measured a 1 MiB burst
  arriving as ~12 KB). The cap manages only what this runtime has received.

## Gates (all green, live tree)

`test_a04_read_budget` 0 · `test_a04_pending_readiness` 0 · `test_a04_parser_pending` 0 ·
`test_a04_daemon_service` 0 · `test_a04_io_surface` 0 · `test_a04_close_state` 0 ·
`test_a04_winpty_backlog` 0 · `test_cell_span_regression` 0 · `test_sgr_stream_regression` 0 ·
`test_partial_write_regression` 0 · `test_terminal_fidelity` 0 · `test_degenerate_inputs` 0 ·
`test_char_width` 0 · `test_cpr_reply` 0 · `test_readiness` 0 · `test_wait_any` 0 ·
`test_wait_change` 0 · `test_visual_change` 0 · `test_daemon_concurrency` 0 ·
`test_perf_contract` 0 · `test_golden_frames` 0 · `test_fx_contract` 0 · `test_version_sync` 0 ·
`test_dependency_sync` 0 · `test_doc_counts` 0 · `_sandbox_fuzz_core` 17 030 iterations, 0 defects ·
`tools/sync_vendor.py --check` 0.

File hashes (first 16): `pty_backend.py d179881ab4f6ab7e` · `session.py dc1a182e484fdb79` ·
`readiness.py d32b936860872223` · `screen_model.py bbd9a20f9d66b1dc` ·
`tui.py 3e1442aff80aa8a6` · `mcp_server.py f89325fffa8ff7ff` · `run_all.py 434952c354b5aec4`.

## Incidents worth recording

* S3's first version made `_snapshot_response` call `sess.io_block()` unconditionally, breaking
  `test_daemon_concurrency`'s fake session. Fixed by making the io block optional and by deciding the
  budgeted-vs-legacy service path ONCE from `sess.io_turn_bytes` (never by catching `TypeError`).
* S5's first version named a local `queue` inside `spawn()`, shadowing the module import and breaking
  the daemon on Windows ("session daemon did not start in time"). Caught by the live ConPTY N1 run,
  not by the unit tests — the reason N1 exists.
* Commit: NOT_CREATED *at the time of writing this receipt*; the release step that follows records the
  commit and tag. Push: requested by the Owner; the harness hook is checked and reported.

---

## Release (end of this round)

| item | value |
|---|---|
| feature commit | `bea017b` — feat(runtime): budgeted I/O, honest observation state, confirmed close (0.3.0) — 36 files, +3912/−121 |
| follow-up commit | `c043eda` — fix(examples,probes): argv lists, environment-aware alt-screen checks, Windows skips |
| tag | `v0.3.0` (annotated, at `c043eda`) |
| version sites | all ten at 0.3.0 (`test_version_sync` green) |
| aggregator | `python tests/run_all.py` → **54/54 passed, RUN-ALL: OK** (148.7 s) |
| push | **BLOCKED** by `~/.omp/agent/hooks/pre/guards.ts` (`git push` is denied unconditionally); Owner runs `git push origin main` + `git push origin v0.3.0` |

The three aggregator failures seen earlier were environment issues, verified rather than assumed:
`drive_vim` (pywinpty shlex-splits a string command, so a vim under `C:\Program Files\...` never
started — now passes with an argv list), `_mcp_probe`'s alt-screen assertion (Git-for-Windows' `less`
never enters the alternate screen here; a synthetic `ESC[?1049h` still sets `alt_screen=True`, so the
decoder is fine), and `_tmux_launcher_probe` (needs `termios`, which Windows does not have). The two
former are now honest checks (model must AGREE with what the program did; a False reading still fails
where the program does enter the alternate screen) and the last SKIPs on Windows like its three
siblings.

**Goal (set by the Owner this round):** reach the highest standard for this product direction —
every claim measured, every limit named, nothing committed that a gate cannot prove. This round closed
the measured liveness/honesty defects (S1–S5 + N1), released 0.3.0, and left S6/A05/A06, N2, W2, W3
and E6 explicitly open rather than implied.

---

## N2 — scheduling edges (found three real defects, all fixed)

The 256 KiB real-pty test never reached these paths; injected runs did, and all three were reachable:

| case | before | after |
|---|---|---|
| a trickling writer that accepts ONE byte per call | 64 calls ran past a deadline that expired after the third and still reported success | the deadline is re-checked before EVERY write; `IncompleteWrite` carries the exact prefix (control: a completed write is never downgraded) |
| `select.select` raising | the OSError propagated raw, losing the bytes already accepted; EINTR was not retried | a wait helper retries the SAME suffix on a signal and reports the earned prefix on any other error |
| a device reply that cannot be written | swallowed by a bare `except: pass` | reported in `io.pending.reply_error` with the known prefix subtracted from `reply_bytes`, attempted once (no blind duplicate), cleared on the next healthy write |

Commit `82ba096`; tests `tests/test_partial_write_edges.py` (7 cases, injected os.write/select/clock,
no PTY) registered in `run_all`. Re-verified on a real POSIX pty after the change: 262 144 B exactly
once, sha256 match, **32** writability waits (32/35/44 across identical runs — the count is
scheduling-dependent, which is the provenance conflict the v3 review raised; the byte-exact result is
what is stable).

## W2 — credible evidence, offline (`W2/`)

`verify_evidence.py` + `credible_fixtures.py` + `test_credible_evidence.py` + `MANIFEST.json`:
8 rule groups, 16 single-lie fixtures, **every falsification rejected by the rule it targets**
(metadata hash, empty manifest, absolute/`..` path escape, missing evidence ref, empty selected text,
hash/length contradiction, `written` with a short payload, `budget_limited` claimed complete, adapter
basis named runtime, hidden provenance conflict, cancel-acked claimed as an exit, `closed_confirmed`
without an observation, replay with gaps, a claim exceeding its evidence level, ConPTY wire-exactness).
`python -B -m unittest discover -s W2 -p "test_*.py"` → Ran 8 tests, OK.
Not built: the `conformance.py` profile extension and `test_conformance_contract.py`
(`new_credible_native_profile: NOT_RUN`).

## W3 — minimal benchmark, offline half (`W3/`)

`judge.py` + `test_bench_min.py` + `MANIFEST.json`: the judge is proven BEFORE any model budget is
spent — 3 tasks × 3 tracks, rejects missing provenance, run mismatch, model drift, track violation,
false completion, missing completion basis, cancel-as-exit, unconfirmed close; an honest failure counts
as a failure, not a rejection. `judge-selftest` → `ok=True, controls=10, escaped=[], wrong_rule=[]`;
`validate` refuses a plan without a spend cap.
**NOT_RUN**: the episode runner, the fixture/adapter files, the second runtime and every model call —
they need an explicitly approved model identity and spend cap plus the single-PTY limits
(≤27 episodes). `episodes_started=0`, `all_agent_results=NOT_RUN`, no simulated score.

---

## S5 real-transport verification: **FAILED — a shipped defect found**

The S5 cap had only ever been exercised against an injected reader (`FakeProc`, which always returns
immediately, so the reader never actually pauses). Driving a real ConPTY child past a deliberately
lowered high water turned that gap into a finding:

| observation | value |
|---|---|
| `pump(max_bytes=64 KiB)` with `SMARTCLI_WINPTY_HIGH_BYTES=131072` / `LOW=32768`, child writing 256 KiB | **never returned** (faulthandler dump at 45 s inside `WinptyBackend._read_budgeted`) |
| same probe, 3 MiB child, high water 256 KiB | did not finish inside its own 120 s deadline |
| control: `read_status()` called once while the child writes | returns in **0.00 s** (the io-evidence path is not the stall) |
| same probe at the **default** high water | N1 measured a 131 072 B burst, below the threshold — no pause, so no stall |

Mechanism: the client waits for its full `max_bytes`, the reader stops filling at the high water, and
the reader only resumes when the client drains — which a client waiting for a budget it can never get
will not do. The two conditions can never meet, so the wait is unbounded.

Repro + evidence: `A04/s5-highwater/{highwater_probe.py,read_status_stall.py}`; tracked as
<https://github.com/dwgx/SmartCLI/issues/15>. Fix direction is in the issue (bounded wait that returns
what is available and wakes the reader on the drain below low water); **not applied in this round**.

**Consequence for the release claims:** S5's "bounded Windows payload" is bounded, but the client-side
budgeted read is not deadlock-free at that bound. The cap's *pause* path is unproven on the real
transport and the client path through it can hang — which must be read as a defect, not as a
verification gap.
