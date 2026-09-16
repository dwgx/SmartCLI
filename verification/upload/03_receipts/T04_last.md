# RUN/T04/last.md — bounded streaming SGR sub-parameter normalization

Worker: session `01a0a700`. Repo `D:\Project\SmartCLI` at HEAD `701e61f` (uncommitted working tree).

## Status: IMPLEMENTED (replaces the earlier chunk-local rewrite)

The previous implementation rewrote every colon in a chunk to a semicolon and only when the whole
sequence happened to sit inside one read. Two consequences, both reproduced by the kit before this
round: `ESC[4:3m` became `4;3` = underline **plus italic**, and `ESC[38:2::255:0:128m` became
`38;2;;255;0;128`, whose empty colour-space slot shifted the operands (fg `00ff00` instead of
`ff0080`). After this round: `conformance --case sgr` → 109 partitions, 7 vectors, **0 mismatches**.

## Exact scope (as delivered)

| file | change | sha256 (first 16) |
|---|---|---|
| `smartcli_core/screen_model.py` | new `_sgr_rewrite_params` + `_ByteStream` streaming filter (states GROUND/ESC_SEEN/CSI/STRING/STRING_ESC/DISCARD, `_CSI_CAP = 1024`) | `242ba3836290a910` |
| `skills/drive-tui/_vendor/smartcli_core/screen_model.py` | byte-identical twin (single-file copy) | `242ba3836290a910` |
| `tests/test_sgr_stream_regression.py` | new: 22 tests | `eb9ce2acb20bd555` |
| `tests/run_all.py` | registration line | `6403122433939712` |

No other module, no dependency, no public API change (the new helper is module-private).

## Required behaviour, as implemented

* Only a **complete and definitely-CSI** `ESC [ … m` is rewritten; anything else is forwarded byte
  for byte. A sequence is held across `feed()` calls until its final byte arrives, so partition
  invariance no longer depends on read boundaries.
* `38:2:<colour-space>:R:G:B` → `38;2;R;G;B` (the optional/empty colour-space slot is dropped rather
  than becoming an empty parameter).
* `4:<style>` → `4`, and `4:0` → `24`; the style sub-parameter is **never** re-emitted as a bare
  code (that is what made `4:3` italic).
* `58` (underline colour, unsupported by pyte) and any unknown sub-parameter group are dropped **as a
  group**. If every group is dropped the whole sequence is removed rather than emitted as `ESC[m` —
  an empty parameter list is a full attribute reset.
* OSC (`ESC]`, BEL or ST terminated) and DCS/SOS/PM/APC (`ESC P/X/^/_`, ST only) payloads are tracked
  so a lookalike inside them is never rewritten; the payload is streamed, never buffered.
* An unterminated CSI is held up to 1024 bytes; past the cap it is abandoned and its bytes are
  swallowed until the next final byte (nothing reaches the grid), and a later valid sequence works.
  A lone trailing ESC or a trailing ESC inside a string is held for exactly one more byte.
* No C1-byte handling: only `0x1b` starts a sequence, so a UTF-8 continuation byte (`0x9b` inside
  U+4E1B) is never read as a CSI introducer.

## Commands and results (first run, no rerun)

| command | exit | result |
|---|---|---|
| `python -B tests/test_sgr_stream_regression.py` | 0 | Ran 22 tests, OK |
| `python -B tests/test_cell_span_regression.py` | 0 | Ran 18 tests, OK (T05 preserved) |
| `python -B tools/sync_vendor.py --check` | 0 | in sync |
| `python -B tests/test_vendor_sync.py` | 0 | PASS |
| `python -B tests/test_terminal_fidelity.py` | 0 | PASS |
| `conformance.py --case sgr --consent-execute-reviewed-code` | 0 | 0 mismatches, oracle `RGB ff0080; underline true; italic false` |
| full memory gate set (14 scripts incl. fidelity, degenerate inputs, CPR, readiness, wait_*, visual change, daemon concurrency, perf contract, golden frames, fx contract) | 0 | all green |
| `tests/_sandbox_fuzz_core.py` (17 030 iterations) | 0 | 0 defects |
| `tools/screenshot/perception_matrix.py` (24 cells) | 0 | 24/24, output redirected to a temp dir |

## Four-stage mutation proof (isolated copy `RUN/T04/validation/repo`)

| stage | component | result |
|---|---|---|
| 1 original | `_ByteStream` restored to the old chunk-local `_SGR_COLON.sub` path | **FAILED (failures=10, errors=1)** — fg `00ff00` ≠ `ff0080`, italics `True`, `58` leak, OSC/DCS lookalikes rewritten; the partition sweeps still passed, which is exactly why the semantic oracle is required |
| 2 candidate | live `screen_model.py` | Ran 22 tests, **OK** |
| 3 bug restored | old path again | **FAILED (failures=10, errors=1)** |
| 4 restored | live `screen_model.py` | Ran 22 tests, **OK** |

Test file bytes identical in every stage (`sha256 eb9ce2acb20bd555…`). The single ERROR is the
white-box `_csi` bound assertion running against a class that no longer has that attribute — an
intended structural difference of the mutation, not a business assertion. Logs: `stage{1..4}-*.log`;
mutation: `../mutate.py t04-old-regex` (anchor asserted unique).

## NOT_RUN

* `native_pty` — `NOT_REQUIRED_FOR_THIS_MEMORY_INCREMENT`.
* `competitor_runtime` — NOT_RUN.
* `run_all.py` whole-suite — heavy suites excluded; gates run individually.
* **Commit: NOT_CREATED. Push: NOT_REQUESTED.**
