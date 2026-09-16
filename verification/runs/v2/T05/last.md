# RUN/T05/last.md — the selected label is 保存, not 3

Worker: session `01a0a700` (owner of the SmartCLI workstream). Kit `D:\Project\SmartCLI-v2-handoff`
(67/67 verified), RUN `D:\Project\SmartCLI-v2-runs`, repo `D:\Project\SmartCLI` at HEAD `701e61f`.

## Status: ACCEPTED-EXISTING + COMPLETED

The cell-span fix was already in the tree, delivered by an earlier worker (claude-sonnet-5 session
`94a696e9`) and reviewed by this session. Per the brief it was **not rewritten**. What this round
added: the v2-mandated task-scoped test file with its control groups, the split of the earlier
combined test file, and the four-stage mutation proof in an isolated copy.

## Exact scope (as delivered)

| file | change | sha256 (first 16) |
|---|---|---|
| `smartcli_core/snapshot.py` | `build_snapshot` aggregates span text from `model.row_cells(y)[a:b]` | `3b6e10af2018c854` |
| `skills/drive-tui/_vendor/smartcli_core/snapshot.py` | byte-identical twin (single-file copy, no refresh) | `3b6e10af2018c854` |
| `tests/test_cell_span_regression.py` | new: 18 tests | `0074e5994f51cd20` |
| `tests/run_all.py` | registration split into two task-scoped entries | `6403122433939712` |
| `tests/test_cell_span_and_split_sgr.py` | **superseded**, archived to `RUN/T05/superseded/` — its T05 cases moved into the file above, its T04 cases into `tests/test_sgr_stream_regression.py` | — |

The archived file is the only deviation from the three-file cap; it is a move, not a deletion: no
assertion was dropped, and keeping a merged T05+T04 file is exactly what v2's ORDER rejects.

## Commands and results (first run, no rerun)

| command | exit | result |
|---|---|---|
| `python -B tests/test_cell_span_regression.py` | 0 | Ran 18 tests, OK |
| `python -B tools/sync_vendor.py --check` | 0 | `vendor in sync with canonical smartcli_core/` |
| `python -B tests/test_vendor_sync.py` | 0 | PASS (8 files byte-identical) |
| `python -B tests/test_terminal_fidelity.py` | 0 | PASS |
| `conformance.py --case screen --consent-execute-reviewed-code` | 0 | expected `保存`, actual `保存`, span `[0,15,19]` |

## Four-stage mutation proof (isolated copy `RUN/T05/validation/repo`)

Test file bytes identical in every stage (`sha256 0074e5994f51cd20…`). The live tree was never
reset, reverted or stashed.

| stage | component | result |
|---|---|---|
| 1 original | `snapshot.py` with `display[y][a:b]` restored | **FAILED (failures=12)**, first business assertion `'3' != '保存'` |
| 2 candidate | live `snapshot.py` | Ran 18 tests, **OK** |
| 3 bug restored | `display[y][a:b]` restored again | **FAILED (failures=12)** |
| 4 restored | live `snapshot.py` | Ran 18 tests, **OK** |

Logs: `stage{1..4}-*.log`. Mutation script: `../mutate.py` (`t05-old-slice`), which asserts its
anchor matched exactly once.

## Controls pinned

ASCII menu; CJK prefix + ASCII label; Japanese prefix; fullwidth digits; emoji prefix; ZWJ emoji;
variation selector; combining mark; a 4-byte UTF-8 char containing a `0x9b` continuation byte; wide
glyphs at column 0 with trailing text; a span reaching the last column; label whitespace (`.strip()`
behaviour unchanged); repeated labels; the cursor-line fallback; and body text not being column-sliced.
Every expected label is a literal; none is computed with the production aggregation.

## Preserved / not touched

Span half-open coordinates, the widest-highlight heuristic, cursor/status hints, JSON field names,
`.strip()` semantics, `INTERLEAVE_OK`/`on_poll`/`resize` deferral, vendor twins, packaging paths.
`screen_model.py`, `session.py`, `tui.py`, `mcp_server.py`, `pyproject.toml` and workflow files were
not touched by T05.

## NOT_RUN

* `native_pty` — `NOT_REQUIRED_FOR_THIS_MEMORY_INCREMENT` (no PTY, no ConPTY, no child process).
* `run_all.py` — not run as a whole: it includes the heavy PTY/effect suites the brief forbids; its
  pure-memory gates were run individually (14 gates, all exit 0).
* **Commit: NOT_CREATED. Push: NOT_REQUESTED.**
