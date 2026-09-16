# SmartCLI — local ground truth, 2026-09-16

Purpose: give a web model (no shell, no local repo) the facts it could not obtain from
reading the repository. Everything below was executed on this Windows box against the
real working tree, or read at an exact line. Nothing here is copied from the plan
package; where the plan already covers a fact, that is stated so the reader does not
treat agreement as new information.

- Repository: `D:\Project\SmartCLI` (git remote `https://github.com/dwgx/SmartCLI.git`)
- HEAD: `701e61f6d69aa2420617edf80b1136df8d5e8cf7` — identical to the plan's baseline
  (`MASTER_PLAN.md` §1). Working tree clean; only `.codegraph/` (gitignored) is local.
- Interpreter used: CPython 3.14.7 (`D:\Software\Developer\Python314\python.exe`),
  `pyte` installed globally (0.8.2). No repo virtualenv.
- CodeGraph index: `.codegraph/codegraph.db`, 199 files / 3 532 nodes / 9 359 edges,
  `codegraph sync` → "Already up to date" (2026-09-16).
- Not available on this box: a running Docker daemon (`docker` CLI 29.7.2 present,
  `dockerDesktopLinuxEngine` pipe absent) and any POSIX shell. All POSIX-only paths
  below are therefore marked **static only**.

Evidence levels follow the plan's own ladder (`docs/05_ACCEPTANCE.md`): E3 = real core
imported, pure in-memory; E2 = extracted logic or stand-in; E1 = source/spec read.

---

## 1. A03 — cell-column slicing of a Unicode display line (reproduced end to end)

Plan reference: A03 / T05. Status: **confirmed, E3, unconditionally wrong for any row
containing a wide character before a highlighted span.**

`smartcli_core/snapshot.py:254` builds highlighted-span text with a Python string slice:
`menu_items.append(Span(y, a, b, display[y][a:b].strip()))`, where `a`/`b` came from
`_contiguous_spans(hi_cols)` — i.e. **terminal cell columns** — while `display[y]` is a
string whose length is `cols` minus the number of wide characters (each wide glyph is
one character but two cells; its continuation cell holds `""`).

Command: `python probe_extended.py D:\Project\SmartCLI` (probe source attached).

```
== which rows break the display[a:b] rule (snapshot.py line ~264) ==
  pure ASCII                   cells[9:11] want='OK'       snapshot-rule-gives='OK'       same
  CJK prefix                   cells[4:7]  want=' OK'      snapshot-rule-gives='K'        WRONG
  Japanese + ASCII             cells[12:14] want=' O'      snapshot-rule-gives=''         WRONG
  emoji before                 cells[4:7]  want=' OK'      snapshot-rule-gives='K'        WRONG
  combining mark               cells[6:8]  want=''         snapshot-rule-gives=''         same
  full-width digits            cells[5:7]  want='O'        snapshot-rule-gives=''         WRONG
  wide inside span             cells[0:6]  want='中文OK'    snapshot-rule-gives='中文OK'    same
```

End-to-end through `build_snapshot` — a three-item Chinese menu with item 2 in
reverse video, fed as UTF-8 bytes into a real `ScreenModel`:

```
  menu, reverse video over '保存'
    span r0[15:19] reported='3' truth='保存' WRONG
    selected.text='3' truth='保存'
```

This is the single most damaging local finding: `Snapshot.selected.text` and
`regions.menu_items[].text` — the fields that exist precisely so an agent does not have
to guess which menu item is active — are wrong for a Chinese UI. The agent is told
"selected = 3" when the highlighted label is 保存. The plain body text (`to_text` lines,
`to_json().lines`) is unaffected; only the column-sliced fields are.

One offset row (`wide inside span`, span starting at column 0) happens to agree: the
error is a per-wide-character shift accumulated from the left, so it is invisible on
pure-ASCII fixtures and on spans that start at column 0 after no wide characters. Any
ASCII-only test suite passes while the defect is live. Confirmed: no test in `tests/`
slices a `display` row by cell column for a non-ASCII row.

## 2. A02 — SGR sub-parameter normalisation is per-read-chunk, not per-stream

Plan reference: A02 / T04. Status: **confirmed, E3, quantified.**

`smartcli_core/screen_model.py:77-81`:

```python
def feed(self, data: bytes) -> None:
    if b":" in data:
        data = self._SGR_COLON.sub(
            lambda m: b"\x1b[" + m.group(1).replace(b":", b";") + b"m", data)
    super().feed(data)
```

The regex `\x1b\[([\d;:]*:[\d;:]*)m` only matches when the **whole** sequence is inside
one `feed()` call. A read boundary inside `ESC[4:3m` or `ESC[38:2::R:G:Bm` passes the
bytes through untouched, pyte then aborts the sequence at `':'` and draws the remainder
as text.

Command: `python probe_extended.py D:\Project\SmartCLI`

```
== A02: SGR split sweep across every byte boundary (all payloads) ==
  curly underline            BROKEN at 5/6 cuts         first_bad=1
  truecolor fg               BROKEN at 15/16 cuts       first_bad=1
  truecolor bg               BROKEN at 15/16 cuts       first_bad=1
  underline colour           BROKEN at 13/14 cuts       first_bad=1
  plain SGR (control)        SPLIT-SAFE
  CSI cursor move (control)  SPLIT-SAFE
  OSC title (control)        SPLIT-SAFE
```

Controls matter: plain SGR, CSI movement and OSC titles are already split-safe, so the
defect is specific to the colon pre-pass, not to pyte's own streaming.

How often it bites in practice — `python probe_split_rate.py D:\Project\SmartCLI`, a
12 395-byte stream of 200 lines, each line carrying one truecolor and one curly-underline
SGR (the Neovim/kitty/delta output the pre-pass exists for), fed in random chunks, 40
seeds per chunk size:

```
  chunk<=      1 bytes : 40/40 streams corrupted ( 100%)
  chunk<=     64 bytes : 40/40 streams corrupted ( 100%)
  chunk<=   1024 bytes : 40/40 streams corrupted ( 100%)
  chunk<=   4096 bytes : 31/40 streams corrupted (  78%)
  chunk<=  65536 bytes :  1/40 streams corrupted (   2%)
```

`feed_errors` stays `0` in the corrupted runs: pyte tolerates the debris, so the
existing "systemic parse failure" counter does not fire and nothing in the product
notices.

Sample corruption (chunk ≤ 7 bytes, seed 7):

```
    trial 0: '2::255:0:0m红色 3m下划线 done   ...'
    reference='红色 下划线 done                ...'
```

Existing coverage that does **not** catch it: `tests/test_terminal_fidelity.py:309-316`
feeds `b"\x1b[4:3mU\x1b[0m"` and `b"\x1b[38:2::255:0:128mU\x1b[0m"` as whole sequences
only. The invariant that is actually violated ("any split of the same byte stream yields
the same cells") has no test.

## 3. A01 — POSIX non-blocking write ignores the byte count

Plan reference: A01 / T03. Status: **confirmed by source read (E1), not executed here.**

```python
# smartcli_core/pty_backend.py:220  (PosixPtyBackend.write)
os.write(self._fd, data)
```

and `spawn()` sets the fd non-blocking at line 184 (`os.set_blocking(master_fd, False)`).
`os.write` returns the number of bytes written; the value is discarded. There is no
retry loop, no `EAGAIN` wait, no deadline. `WinptyBackend.write` (line 125) delegates to
`pywinpty` and is unaffected.

Not verifiable on this host: no POSIX shell, Docker daemon stopped. The repository
already ships a POSIX harness (`tests/_sandbox_posix_backend.py`) that drives a real
`pty.fork()`; it does **not** exercise short writes. The plan's claim (extracted-logic
stand-in: "planned abcdefgh, received abc, 1 call") is consistent with the source but is
E2, not E4 — nobody has yet seen this on a real Linux pty.

## 4. A04 — the idle daemon never drains the PTY (platform-dependent consequence)

Plan reference: A04 / T07. Status: **confirmed by source read, E1.**

`skills/drive-tui/scripts/tui.py:534-538` (worker thread of `_serve_forever`):

```python
try:
    item = jobs.get(timeout=0.2)
except queue.Empty:
    continue            # <- no sess.pump() on this path
```

Only request handlers call `sess.pump()` (`_handle`, lines 291 / 344 / 700). So while no
client is asking, nothing reads the child's output. The consequence differs by backend:

- **Windows (`WinptyBackend`)**: a dedicated reader thread already drains ConPTY
  (`_read_loop`, line 96-107) into `self._queue = queue.Queue()` (lines 72 / 83) — an
  **unbounded** queue with no byte budget. The child does not block; the daemon's RSS
  grows with total output while idle, and pyte never parses it, so the first later
  `snapshot` pays one huge `feed()`.
- **POSIX (`PosixPtyBackend`)**: nobody reads the master fd at all while idle; a child
  that keeps writing fills the pty buffer and blocks. Device-query replies are also
  answered only from inside `pump()`, so a child waiting for a cursor-position report
  while the agent is away stays stuck.

The plan states this as "idle daemon has no continuous pumping; POSIX drain and Windows
queue lack budgets". The refinement that matters for the fix and its test: on Windows it
is a memory/tail-latency defect, on POSIX it is a liveness defect. The two need different
negative tests, and only the Windows half is runnable on this host.

## 5. A05 — "64" is a filter, not an admission cap

Plan reference: A05. Status: **confirmed by source read, E1.**

`skills/drive-tui/scripts/tui.py:601-603`:

```python
readers.append(t)
if len(readers) > 64:  # bound the thread count; finished ones drop out
    readers = [x for x in readers if x.is_alive()]
```

Threads are appended unconditionally; exceeding 64 only prunes finished entries. A peer
that connects and holds the socket open (the read path has `PRE_AUTH_TIMEOUT = 2.0`,
line 374, which bounds the *pre-auth* read but not the thread's lifetime after a failed
auth, and not the eventual `_reply` `sendall`) keeps its thread alive and the list grows.
There is no refusal path here; the only real cap is `SMARTCLI_MAX_SESSIONS`
(daemon count, default 8, max 128), which is a different resource.

## 6. A06 — worker-thread reply path, and one mitigation the plan does not mention

Plan reference: A06. Status: **partly confirmed, E1; the plan understates one existing fix.**

`_reply` (line 418) does `conn.settimeout(POST_AUTH_TIMEOUT)` then `conn.sendall(...)` on
the caller's thread; `POST_AUTH_TIMEOUT = 60.0` (line 376). A peer that stops reading can
therefore stall the single session worker for up to 60 s per reply. Bounded, but not
small.

What the plan does not mention anywhere (`grep -rn interleave docs/ MASTER_PLAN.md
LOCAL_AGENT_PROMPT.md` → no hits): the daemon **already** implements partial
multi-watcher behaviour. `_serve_forever` defines

```python
INTERLEAVE_OK = frozenset({"snapshot", "alive", "list", "send_text", "send_line", "send_keys"})
```

and `_drain_interleavable()` (lines ~485-530) answers exactly those verbs from inside the
running wait's poll gap, on the worker's own thread, keeping the single-writer invariant.
`resize` is deliberately excluded with a documented reason (a resize changes the content
hash and would make a concurrent `wait_change` report the caller's own resize as a
screen change). Any R2 redesign of the owner loop must preserve both behaviours and the
documented rationale, or it regresses a fixed defect. This is the clearest case where the
plan's architecture section is written as if `tui.py` were still the naive version.

## 7. Repository facts the plan's `01_REPOSITORY_TOUR` does not state

- **The core is duplicated.** `smartcli_core/` is canonical and
  `skills/drive-tui/_vendor/smartcli_core/` is a vendored copy; `tests/test_vendor_sync.py`
  is the gate and `tools/sync_vendor.py` the writer. Every fix in `smartcli_core/` must be
  synced or the gate fails. `codegraph impact PosixPtyBackend.write` returns only the
  vendor twin, which is a useful reminder that CodeGraph's call graph is best-effort
  (the production call path is `PtySession.send_text → backend.write` via the abstract
  base, which it does not resolve).
- **Size**, measured with `git ls-files '*.py'` + line counts: 497 tracked files, 177
  Python files, 34 356 Python lines total, split `tests/` 9 991 (53 files), `skills/tui-ui`
  5 553 (24), `skills/cmd-art` 4 600 (42), `tools/` 4 544 (20), `skills/drive-tui` 3 850
  (17), `_vendor` copy 2 495 (7), `smartcli_core/` 2 495 (7), examples 157 (1). The
  vendored core is byte-for-byte the same size as the canonical one. `HANDOFF.md` alone is
  158 KB and `NEXT-STEPS.md` 55 KB — the plan is right that these must be read by section.
- **Documentation search outcome**: `grep -n "short write|partial write" HANDOFF.md
  NEXT-STEPS.md README.md CLAUDE.md AUDIT-REPORT.md` → **no hits**; likewise for CJK cell
  span. Neither A01 nor A03 is recorded anywhere in the repository's own history, so
  neither is a re-discovery of a known issue.

## 8. Plan package: what actually runs on this box

- `python tools/agentctl.py verify-kit` → `{"ok": true, "checked_files": 49,
  "mismatches": []}` (also implies the `--run` directory discipline can be applied).
- `python -m unittest discover -s tests -v` in the plan package → **47 tests, OK,
  1 skipped** ("symlinks not permitted by this OS account"). The plan's "47 self-tests
  passed" claim is accurate on this machine.
- The 20 audit findings (A01–A20) are present as machine-readable records in
  `legacy/audit_findings.json`, each with `location`, `evidence`, `impact`, `fix`,
  `acceptance`. The `docs/02_CODE_AUDIT.md` file referenced in the original chat answer
  is **not** in this zip, but `legacy/audit_findings.json` carries the same content in a
  more useful form — no re-download needed.
- Missing from `C:\Users\dwgx1\Downloads` (referenced in the chat but never saved):
  `SmartCLI_Audit_and_Upgrade_Handoff_2026-09-15.zip`, `SmartCLI_SCORECARD.xlsx`,
  `AI_HANDOFF.md`, and `Agent_Terminal_Research_2026-09-15.zip` (the 58-entry atlas).
  The scorecard is the only unique content there; the audit and the atlas are superseded
  by `legacy/audit_findings.json` and by `docs/12_SOURCES.md`.

## 9. What is still unverified after this pass

| Claim | Level now | Needs |
|---|---|---|
| A01 short write on a real pty | E1 | a Linux container or WSL run of `_sandbox_posix_backend.py` with a short-write stand-in |
| A04 child-blocking while idle (POSIX) | E1 | same Linux run, child writing continuously with no client polling |
| A04 unbounded Windows queue growth | E1 | a loopback/fake session test asserting a byte budget |
| A05 thread growth past 64 | E1 | loopback test holding connections open |
| A06 60 s worker stall | E1 | loopback test with a non-reading peer |
| Real ConPTY session behaviour end to end | not run | this host can do it, one PTY at a time, only with explicit approval |
| Competitor rows in the scorecard | doc-level only | nobody on this box has run any competitor |
