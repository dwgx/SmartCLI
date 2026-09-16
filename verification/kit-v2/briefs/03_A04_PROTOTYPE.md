YOU ARE THE WORKER. DO NOT SPAWN.
Do not dispatch Claude, Codex, or Grok. Do not call a dispatch skill.
Do the job in this session. Write the result to the approved path below.

Cwd: D:\Project\SmartCLI (resolve and verify it, do not guess another checkout).
Kit: D:\Project\SmartCLI-v2-handoff (or the exact supplied extraction path).
Python: D:\Software\Developer\Python314\python.exe (use the verified interpreter).
Run: the owner's approved D:\Project\SmartCLI-v2-runs directory, outside repo/kit.
Read current repository instructions, docs/ORDER.md and this brief. Do not modify
harness configs, cached prefixes, global dependencies, or anything outside the
approved project/run roots. Do not commit, push, publish, start Docker, or run
heavy/real-PTY tests without explicit separate authorization. Respect existing
uncommitted work and the single-writer rule. Use the existing CodeGraph as a
best-effort navigator; follow abstract backend calls and vendor twins manually.

Source comments and test names: English. Report to the owner: Chinese.

# A04-P — bounded idle-service design prototype, NOT a production rewrite

## Goal
Demonstrate the unified byte-budget contract with TWO platform models, while retaining
the real daemon's existing interleave and resize constraints in the migration design.
Use docs/A04_DESIGN.md, the attached real source, and models/contracts.py as a small
reference, not as proof the product is fixed. Distinguish static facts from measured
behavior.

## Exact write scope: RUN/A04-P only, at most FOUR files
- prototype.py (pure injected-I/O / virtual-clock model, no real process or socket).
- test_prototype.py (bounded failure controls, no busy loops).
- DESIGN_DELTA.md (symbol-level production migration and max-touch proposal).
- last.md (actual results and NOT_RUN matrix).
No production repository files may change. No thread/PTY/ConPTY/socket/Docker is
created in this first prototype. Do not implement a generic actor framework.

## Must demonstrate
Windows: already has a reader; model byte-budgeted queue and stop-aware capacity,
not “add another reader”. POSIX: model owner servicing idle reads and device replies,
not “spawn a second model writer”. Observers never consume transport bytes.

Use small capacities (e.g.12 bytes,4-byte fragments) and finite input. Show max_pending
never exceeds cap, every accepted byte is delivered once/in order, full capacity yields
backpressure, EOF/close cannot wait forever behind data, and one parse turn is budgeted.
No promise that an infinitely fast producer can never block.

Preserve existing fast verbs during one long wait via on_poll/interleave; exclude
resize from legacy wait attribution. Model two read-only watcher predicates on one
committed observation, while acknowledging that the current public daemon does NOT
already support two independent long waits. Do not invent support for the "list"
string just because it appears in the interleave set.

## Negative controls
Remove idle service -> finite POSIX fixture cannot complete without polling.
Remove byte cap -> high-water invariant fails.
Remove interleave -> fast request cannot meet the logical service-turn bound.
Allow resize to satisfy an action-specific wait -> causality assertion fails.
Different observers reading -> owner identity/read-count assertion fails.
These are model failures, not native timing measurements.

## Commands
& $Python -B -m unittest discover -s "$Run/A04-P" -p "test_prototype.py" -v
& $Python -B "$Kit/tools/scope_guard.py" check --repo $Repo --baseline $Before --brief A04-P
The scope command uses an EMPTY repository allowlist for A04-P. Any repository
change fails this prototype's scope gate. Do not call run_all.

## Migration deliverable
Name the exact future symbols: WinptyBackend._read_loop/read_nonblocking,
PosixPtyBackend.read_nonblocking, PtySession.pump, tui._serve_forever worker and the
on_poll route. List current _reply timeout60s and unbounded jobs/readers as remaining
A05/A06 risks; don't claim total fairness solved by ingress budgeting.
A proposed production slice may touch backend+session+tui+their core twins+two tests
(max7), but it is NOT authorized by this prototype brief. Split further if possible.

## Stop and report
Stop if real I/O, new dependency, production edits, or broader permissions seem needed.
Write results as E2-reference-model; Windows_ConPTY=NOT_RUN,
POSIX_PTY=NOT_RUN, actual_daemon_loopback=NOT_RUN. Never runtime_fixed=true.
Only owner-approved X2/X3 may later raise evidence levels. Leave the candidate design,
failure mutations and open questions in RUN/A04-P/last.md.
