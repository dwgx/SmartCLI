# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.5] - 2026-10-01

The review of 0.3.4 — the code that review itself produced, and had therefore
never been attacked by anyone who did not write it. Two of these four are gates
that could not fail.

### Security
- **A close-path exception message reached the log verbatim.** `sessionlog`'s
  `payload_attrs` docstring certifies that every text-bearing attribute routes
  through one funnel. `last_progress` did not: `_describe_close` wrote
  `str(result.get("last_progress"))[:200]` under *every* policy. Measured under
  the documented scrub-everything mode, a `session.close` event carried
  `close_state raised OSError: failed to spawn: ssh root@host --password
  hunter2`, and the secret was in `to_ndjson()`. `session.py:333` builds that
  string as `f"close_state raised {type(exc).__name__}: {exc}"` and
  `pty_backend.py:385` as the `terminate` equivalent — an exception message,
  exactly the class `error_attrs` exists to scrub. Now routed through
  `payload_attrs`, keeping the 200-character bound. A sweep for every other
  verbatim-written attribute in the module now returns **zero**.
- **The `record_snapshots` consent gate had been made vacuous by the change
  that closed the previous leak.** It asserted the literal key `screen_text`
  is absent — but routing the text through `payload_attrs` means the raw key
  can never appear under the default policy, whatever `record_snapshots` says.
  Deleting the consent gate entirely left the suite green, and with
  `record_snapshots=False` (the default) every wait event grew a 132-character
  screen digest and a fingerprint: `to_text()` paid with no consent, exactly
  what the module docstring denies. The check is now a **prefix** check — no
  attribute whose name begins with `screen_text`, whatever the policy would
  have spelled it.

### Fixed
- **The path-component boundary was the inverse of what its own comment
  claimed.** Added in 0.3.4 to stop a *sibling* directory (`SmartCLI-v3-runs`)
  being flagged as this checkout, it flagged only when the tail was a separator
  or nothing and skipped everything else — so the most natural prose forms of
  naming the path escaped the ban entirely: `D:\Project\SmartCLI before
  pushing`, `` `D:\Project\SmartCLI` ``, `(D:\Project\SmartCLI)`,
  `D:\Project\SmartCLI, which is`. The sibling false positive had been removed by
  making the rule **narrower than the rule it documented**, which is the same
  class of hole as the one 0.3.4 was fixing. A tail that is alphanumeric or one
  of `-_.~` now means "a longer directory name" and is skipped; everything else
  is flagged. Eight probes pin it, and the wider rule produced **zero** new
  findings across the real 172-document corpus.
- **The derived `INVALID_HANDLE_VALUE` sentinel had no gate at all.** Three
  mutations of it left the suite green. It is now pinned to
  `c_void_p(-1).value`, proved **not** to be `-1` (the old form, which could
  never fire because ctypes hands back the unsigned pointer value
  `18446744073709551615`), and bound to the `c_void_p` restype it exists to
  interpret.

### Notes
- Each fix carries a red-proof. For the boundary: reverting the rule to its
  0.3.4 form turns four probes red while the two sibling probes stay green. For
  the consent gate: deleting `and log.record_snapshots` turns it red with
  `leaked=['screen_text_chars', 'screen_text_sha256_16']`.
- Verified with 12 deterministic gates, `ruff check --select E9,F63,F7,F82 .`,
  `mypy --platform linux`, and the four-leg CI matrix — all green. The full
  `tests/run_all.py` is not re-run for this release; the changes are in the
  session log, three gates and the version sites, and the last full run was
  62/62 on the 0.3.3 tree under the Owner's standing consent.
- The pattern across 0.3.3 → 0.3.5 is worth stating plainly: **each release's
  review found defects in the release just made.** Three of the nine across
  the three passes were gates reporting a false pass, and two more were a gate
  whose rule was the inverse of its own comment and a gate made vacuous by the
  very change that closed the bug it watched. The standing standard — *a green
  check is only evidence if it can turn red* — is what keeps finding them, and
  it is not yet demonstrably exhausted.


## [0.3.4] - 2026-10-01

The close-out review of 0.3.3, run after 0.3.3 was already tagged and published.
Every defect below was found by review, and two of the four are cases where a
green check was actively reporting a false pass.

### Security
- **Screen text bypassed the payload policy entirely.** `sessionlog` assigned
  `described["screen_text"] = _screen_text(snapshot)` verbatim, gated only on
  `record_snapshots`, so a credential echoed on screen landed in the log under
  **every** policy — including the documented scrub-everything mode — while the
  new `payload_attrs` docstring certified that screen text was one of the
  fields routed through the single funnel. That sentence was promising something
  the code did not do. Screen text is now routed through the policy: a length
  always, a fingerprint under the default `hash`, the text only under an
  explicit `full`, and a bare length under `none`. A screen is the most likely
  place a driving session shows a secret, but it is also where the forensic
  question lives — *"did this wait see the screen it saw last time, or a
  different one?"* — and a digest answers that without writing the screen down.
  The screen's **shape** is not lost either way: rows, cols, selected line,
  alt-screen, title and status-bar lengths are already recorded free on every
  event, by default.

### Fixed
- **A crashing test was reported as a PASS, and every test after it never ran.**
  The worker-thread wrapper added in 0.3.3 caught only `VirtualRunaway`, so any
  other exception propagated out of the thread target, was printed by
  `threading.excepthook`, left the failure list empty — and `main()` printed
  `PASS` and returned 0. `run_all.py` reports on exit code alone, so the
  aggregator counted the file green too. This inverted the change's own comment,
  which said the wall-clock horizon exists *"so one runaway cannot hide the
  state of everything else"*: a crash now hid everything after it, where the
  pre-patch plain loop had at least died loudly. All exceptions are now recorded
  as named failures. Red-proven at both an early and a **last** position, where
  nothing follows to expose the crash.
- **The dev-box path ban depended on where the clone lives.** `BANNED_PATHS` is
  derived from the checkout's own location, and a raw substring match also
  swallowed a **sibling** directory whose name merely begins with it — on a
  Windows box `D:\Project\SmartCLI` matched `D:\Project\SmartCLI-v3-runs\`. So
  the same commit passed locally and failed on all four CI legs, where the
  workspace is the runner's path. The match now ends at a path component: a
  separator, or nothing.
- **`_scan_banned_paths` missed the second path on a line.** It used
  `re.search`, which returns only the first match, so a second dev-box path
  appended to an already-flagged line was invisible — an exemption could
  launder whatever else sat beside it. Now `finditer`.
- **The published gated-suite count was decremented, not re-derived.**
  `CLAUDE.md` said 46 of 62; the derivation gives **47 of 62** and **15**
  local-only. The arithmetic proves it: the entry the 0.3.3 cut removed
  (`python -m ui.box_junction`) was itself ungated, so removing it should have
  moved only the denominator. `CLAUDE.md` now carries the derivation and the
  instruction not to decrement it again.
- **The release-ref check accepted `v0` and `v9`**, because it matched a name
  that *looked* like a version; a **branch** named `v0.3.3` produces the same
  `github.ref_name` as the tag. The hole was closed downstream by the
  `refs/tags/` fetch, but the two gates disagreed about what a release ref is. It
  now requires a real tag.
- **`ci.yml`'s derivation recipe did not reproduce its own numbers** (52 files
  claimed, 57 measured; 44 AST-clean claimed, 49 measured), and its final step
  landed on 24 only because two errors cancelled. The recipe is corrected.
- **HANDOFF §0 named v0.2.3 as current**, which 0.3.3 widened to a four-version
  gap beneath a file that calls itself the authoritative current-state record.
  §0 and its header now name 0.3.3 and §10o.

### Documentation
- **`NEXT-STEPS.md` carried five items marked `[OPEN]` that 0.3.3 had already
  finished** — the same commit that wrote the block had closed them. A fresh
  session reads that file first and would have redone finished work.
- **The dev-box path gate could not see the two instances it was written for.**
  `PORTABLE_DOC_GLOBS` omitted `HANDOFF.md` and `NEXT-STEPS.md`, which is exactly
  where the archive pointer went; injecting the path there left the gate green.
  Both are now scanned, with the project's existing box-local disclaimer
  convention preserved rather than erased — 172 portable docs, up from 166.
- **Two counts in the published 0.3.3 notes were wrong and are corrected here
  with a dated erratum**, so a reader of 0.3.3 can see both the claim and the
  correction: *"nineteen documents"* is not derivable (9 mention `color_model`,
  22 "degrade", 26 the union — the delta actually touched 10 degrade lines and 11
  `box_junction` lines), and *"three documents"* is two, with four occurrences.
- **The ACE-type comment misnamed four types against the header it cites.**
  `0x0E` is `SYSTEM_ALARM_CALLBACK`, not `SYSTEM_MANDATORY_LABEL` (that is
  `0x11`), and `0x10` is `SYSTEM_ALARM_CALLBACK_OBJECT` (not
  `SYSTEM_RESOURCE_ATTRIBUTE`, which is `0x12`). The classification was already
  correct — the fix is to the evidence, in the file whose purpose is to be the
  evidence.
- **The `INVALID_HANDLE_VALUE` comparison could never fire.** Written as
  `== -1` while the restype is `c_void_p`, so ctypes hands back the **unsigned**
  all-ones pointer (measured: `18446744073709551615`) and the guard was dead —
  while the comment claimed the opposite. The sentinel is now derived from
  ctypes. Impact was bounded, because a failed snapshot still fails closed via
  `Process32FirstW`, which is why no gate caught it.

### Notes
- **Every fix carries a red-proof**, including the credential one: forcing the
  screen-text policy to `PAYLOAD_FULL` puts `password: hunter2` in the serialised
  log and turns three checks red.
- Verified with 21 deterministic gates, `ruff check --select E9,F63,F7,F82 .`,
  `mypy --platform linux`, and a four-leg CI matrix (Windows/Linux/macOS ×
  py3.10/py3.14) — all green.
- The full `tests/run_all.py` was last run on the **0.3.3** tree (62/62, exit 0,
  3m34s, with real PTYs, under the Owner's standing consent). It has **not** been
  re-run for this release, which changes session-log, doc gates and the version
  sites but no runtime path the suite exercises differently; the 21 deterministic
  gates and the four-leg matrix are the evidence for 0.3.4.

## [0.3.3] - 2026-10-01

This release is the output of an adversarial review pass over 0.3.2 and the
capability work that followed it. Most of it is fixes to things 0.3.2 shipped;
the defects below were found by review, not by users.

### Added
- **A child that dies mid-wait now ends the wait, instead of costing you the whole
  timeout. Opt in, and off by default.** `smartcli_core` grew a first-class
  child-death outcome (`readiness.EXITED`, a falsy singleton whose equality is
  identity-only, plus a `reason` of `EXITED` for `wait_ready`) in the previous
  release, and it reached nobody: the daemon's five wait call sites passed
  neither the session flag nor a per-call predicate, so a program that crashed
  on your first input still burned the ceiling. Measured before the wiring, with
  a dead child and a virtual clock: **30.00 s of a 30 s ceiling** in
  `wait_ready`, `wait-regex` and `wait-any` alike. The session-level opt-in is
  `start --detect-child-exit` (CLI), `run --detect-child-exit` (one-shot), and
  `detect_child_exit` on the MCP `start` tool. **Off is exactly the previous
  behaviour**, byte for byte — a wait that used to return `TIMEOUT`/`false`
  still does — and off is the default on every verb.
  On, every wait reply carries `exited`, and `wait` reports `reason=EXITED`.
  `exited` is a *new* key rather than a redefinition of an existing one because
  `EXITED` cannot be sent: it is a singleton, `json` refuses it, and `index >= 0`
  on it raises — so a child dying during `wait-any` would have become a daemon
  *error* rather than the cheap outcome the feature exists to provide. The
  primitive's own return value is therefore coerced to whatever that field's
  wire already spells as "no match" — `false` for the three boolean waits, `-1`
  for `wait-any` — and the distinction travels in `exited` instead. The `-1` is
  load-bearing rather than cosmetic: `False >= 0` is `True` in Python, so
  collapsing `EXITED` to `false` in `wait-any` would have reported
  `matched=true pattern=0` for a wait that matched nothing. The CLI reports
  `exited=` on the same stderr line the other outcome fields already use,
  because `--json` prints the Snapshot payload and not the reply envelope.
  The flag is recorded in the session registry, so `list` can never describe a
  session differently from the one it is listing.
  Gated by `tests/test_drive_security.py` (no PTY, no spawned process): the
  default-is-off invariant, the reply contract for all five waits, and the
  assignment into the live session.
- **Three of the four new core capabilities are deliberately NOT on the CLI or
  MCP surface.** Stating that here rather than leaving it to be discovered is the
  point; a capability on the library surface that nothing reaches is weight, and
  this project has a documented history of shipping prose that implied otherwise.
  - **Screen-revision wait baseline** (`PtySession.screen_revision()`, and
    `after_revision=` on the waits) — **library-only.** Its value is capturing the
    revision at the instant you read the screen, with no round trip in between;
    over a socket the daemon adds two round trips between capture and use, which
    is exactly the weakness the anchor exists to remove. The daemon's existing
    `wait-change --baseline-hash` already provides the "did my action land?" axis
    for remote callers, and adding a second, finer baseline would be surface
    without a consumer.
  - **Terminal-mode registry** (`ScreenModel.mode(name)`, `.modes()`,
    `MODE_REGISTRY`, nine modes) — **library-only.** It needs no new verb to be
    reachable, but nothing an agent can *do* changes with it: the one mode that
    changes what the next action means, `alt_screen`, already travels with every
    snapshot reply, and the one that changes key encoding, `app_cursor`, is
    already honoured inside `KEY_MAP`. What remains is diagnostic value, which
    is not worth nine new keys on every observation.
  - **Session event log** (`smartcli_core.sessionlog` — opt-in JSON Lines, a
    payload policy, retention and a query API) — **library-only.** It is by far
    the heaviest of the four, it adds a disk-write surface carrying whatever the
    driven program printed and whatever you typed at it, and its consumer is a
    human reconstructing a past run — which
    `skills/drive-tui/references/LIMITATIONS.md` already is. Not on a shipped
    verb surface for a release being closed out.

### Security
- **On Windows, the session registry was not private, and the code's own protection there was inert.**
  The per-session registry file holds the capability token that grants full control of a live child
  process. It was created under `%TEMP%`, and everything the code did to protect it is a no-op on
  Windows: the `0o600` passed to `os.open` buys no POSIX mode, and the `0700`/`chmod`/symlink/ownership
  block in `_ensure_reg_dir` is on the POSIX branch, which the `os.name == "nt"` case returned
  *before*. What actually decided access was the ACL of the temp directory, inherited rather than
  chosen -- and it was not an owner-only ACL. Measured on the Windows dev host with `icacls` against a
  live registry file: ten trustees, all inherited, seven granted Modify, one of them a local
  agent-sandbox group. "Only the owner can read the capability token" was false on that host while the
  code claimed it. Three changes, because no one of them is sufficient:
  - **Relocated.** The registry now lives at `%USERPROFILE%\.smartcli\sessions`, whose parent SDDL
    carries inheritable Full ACEs for `SYSTEM`, `Administrators` and the owner and nothing else, so a
    fresh child inherits owner-only-and-admin by construction. The POSIX path is unchanged.
  - **An explicit DACL.** The directory's DACL is replaced with exactly three trustees -- this account,
    `NT AUTHORITY\SYSTEM` and `BUILTIN\Administrators`, full control, inheritable so that a registry
    file cannot pick up a trustee nobody chose -- and is set `PROTECTED` so nothing is pushed onto it
    from its parent. The same DACL is set explicitly on each registry file. Set, not inherited: a
    sandbox agent re-ACL'ing a freshly created directory after the fact was measured on 7 of 9
    sampled profile subdirectories on that host, so relocation alone is a delay, not a fix.
  - **Verified, and failed closed.** `_ensure_reg_dir` reads the effective DACL back, walks its ACEs,
    and refuses to write a capability token if anything outside those three trustees can read or modify
    it -- or if the DACL cannot be read back, which is treated as unproven rather than as clean. The
    refusal names the path, the offending trustees and the `icacls` command to run; point
    `SMARTCLI_TUI_DIR` at a directory your endpoint agents leave alone if the default is re-ACL'd under
    you. A false "still permissive" costs one command; a false "private" leaks a token that drives a
    live child, so the unproven case is the refused one.
  - `tests/test_drive_security.py` now measures the resulting DACL with its own `ctypes` reader --
    deliberately built in the most permissive parent available, so a green run can only mean the code
    replaced the inherited ACL -- and covers the fail-closed refusal, the read-back disagreement, and
    the fact that the POSIX branch is untouched and never reaches the Windows code.

### Changed
- **Sessions started by a previous version are stranded by the relocation, and you must kill them
  yourself.** The old registry is neither read nor written any more, so those sessions are unreachable
  from both `close` and `list`, and their pids -- the only handle left on their child processes -- went
  with them. Every command now warns once on stderr, naming the old path, how many entries it holds
  and their pids. **Nothing is killed for you and nothing is migrated**: a pid read out of a file this
  version cannot see is not this program's to act on. The session cap starts fresh in the new
  directory and is not charged for the stranded entries. If you are upgrading with a session running,
  take the pids off the warning and kill them before relying on `list` again.

### Fixed
- **The DACL privacy check failed open on a granting ACE type.** `tui.py`
  classified `0x09` as an inert ACE. `0x09` is `ACCESS_ALLOWED_CALLBACK_ACE_TYPE`
  — a *granting* type — so a foreign trustee's grant was parsed past and
  `_win_verify_private` declared the directory private. Reproduced on Windows:
  `icacls` reported `BUILTIN\Users` holding `WRITE_DAC`, `WRITE_OWNER` and
  `DELETE` while the check passed. A stranger who can rewrite the DACL could then
  read the capability token. The rule is now inverted rather than patched:
  granting types are enumerated (`0x00`, `0x04`, `0x05`, `0x09`, `0x0B`) and the
  walk is deny-by-default, so a granting type that is not a plain
  `ACCESS_ALLOWED` returns *refused*, and so does any type in neither table —
  an ACE shape nobody enumerated is refused rather than waved through.
- **The "identity-aware" liveness check could not change any outcome.** After
  `if not _pid_is_alive(pid): return False`, every remaining branch returned
  `True`, so the verdict was exactly `_pid_is_alive(pid)` — unchanged from before
  the patch. An exhaustive 72-case cross-product flipped it zero times, and
  overwriting only `pid` in a live registry entry orphaned the running daemon,
  which is the v0.2.2 defect the change claimed to fix. The recorded creation
  time is now consulted where it is authoritative: when the pid is gone, `close`
  enumerates the process table and keeps the entry if any live process carries
  it. Two fail-closed rules stop an unfinished search from reading as evidence
  — an incomplete enumeration, and a search that read zero creation times, both
  mean *could not rule it out*. Measured cost: 759 pids in 19.9 ms, paid only on
  the close-failure path.
- **`payloads="none"` did not govern `error_message`.** The session log's
  docstring named error messages as governed by the payload policy, but that one
  field was merged in unconditionally. A spawn failure — which quotes the
  command line it was handed, password included — landed verbatim in a log the
  module says "outlives the session by years". It is now routed through the same
  policy as every other text-bearing field, with the length cut applied first so
  the digest names exactly the text `payloads="full"` would have written.
- **Mouse encoding modes swallowed delete-line.** Mouse *tracking* modes
  (`9`/`1000`/`1002`/`1003`) and *encoding* modes (`1005`/`1015`/`1006`/`1016`)
  shared one set, and the union gated the X10 branch. So `?1006h` alone — an
  encoding, no tracking — made `ESC[M` (byte-identical to delete-line) get
  consumed as a mouse report: three content bytes eaten, wrong grid, no error
  signal. The realistic trigger is a program that enables `?1000h ?1006h` and
  later disables only the tracking mode. Tracking now gates the branch; the
  encoding stays reported, so a consumer can refuse rather than guess.
- **The wrapper parity test could not see a dropped argument.** The session-log
  wrapper mirrors ~15 methods, and its parity check compared signatures and
  defaults but never the forwarding body — so a keyword accepted and silently
  not forwarded passed it. All recorded methods are now driven through a spy and
  each observed call bound against `PtySession`'s own signature.
- **`_PYTE_CSI_PARAM_BYTES` claimed to be what pyte can carry and omitted seven
  bytes it does.** The set is now pyte's real carry set, and the test derives it
  by driving pyte instead of restating the constant — a test that restated the
  constant could not detect a wrong-but-self-consistent alphabet.
- **An invariant asserted in three places had no gate that could fail it.**
  "The anchor gates success only, never the deadline" is claimed in
  `readiness.py`'s module docstring, at the anchor, and in `wait_ready`'s
  docstring. Mutating the line it is about left the suite green — including the
  gate literally titled *respected max_wait ceiling*, which supplies no
  `changed_since`. The check now exists, with a virtual-clock horizon and a
  wall-clock budget, because the failure mode of a missing deadline is a *hang*
  and a hang cannot fail a gate.
- **`workflow_dispatch` published to production with neither release gate
  running.** Both gate steps were push-only and the `verify` job had no
  job-level `if`, so a manual dispatch reached PyPI through the same OIDC
  Trusted Publisher having run neither the tag-ancestry check nor the
  version-agreement check. The version half now runs on both paths; the ancestry
  half is genuinely unanswerable without a tag and is marked as such rather than
  implied.
- **The capability token's file DACL was set but never verified.** The
  *directory* was applied and then verified both ways; the *file* holding the
  token only had it applied. The capability got the weaker of the two
  treatments. Both are verified now, and both refuse.
- **Two documents told readers to run a command that exits 1.** `HANDOFF.md`
  (twice — §2's regression block at line 177 and the record at line 1944) and
  `docs/MACOS-VERIFY.md:65` instructed `python skills/tui-ui/ui/box_junction.py`,
  which fails with `ImportError: attempted relative import with no known parent
  package`; the module needs `-m`. All three occurrences are removed.
  > **Erratum (2026-10-01):** this entry shipped as "**Three** documents told
  > readers to run a command that exits 1". The count was wrong: **two**
  > documents carried **three** runnable occurrences — `HANDOFF.md:177`,
  > `HANDOFF.md:1944` and `docs/MACOS-VERIFY.md:65`. Measured at the
  > pre-release base with
  > `git grep -n "ui.box_junction.py" b0b660c -- '*.md'`, which returns four
  > lines: those three plus `skills/tui-ui/SKILL.md:316`, which only *names*
  > the file and told nobody to run it. The defect itself was real and all
  > three occurrences were fixed in this release; only the number was wrong.
  > Left visible rather than silently rewritten, so a reader of the published
  > 0.3.3 sees both the claim and the correction.
- **A dev-box path gate banned one literal, so a doc could name the
  developer's home directory and pass** — which a new archive pointer did. It now
  bans the class, and is derived from the checkout so it cannot go stale.

### Removed
- **`ui/color_model.py` and `ui/box_junction.py` (413 lines, unwired).** The
  truecolor→256→16→mono downgrade ladder and the border/edge algebra both
  shipped through 0.3.2 with **zero importers**, and `tui-ui` has no pkgutil
  auto-discovery over `ui/` (that is `fx.registry` and `patterns.registry`,
  neither of which scans `ui/`), so no caller could ever have reached them.
  `Canvas.to_ansi()` emits truecolor `38;2` unconditionally and the string
  `38;5` appears nowhere in the skill, so the ladder's middle tier was never
  emitted; and the live border path is `BOX_STYLES`/`draw_border` in `core.py`.
  Both were correct and self-tested, which is not the argument against them —
  the argument is that a capability with no consumer is weight, and nineteen
  documents had been edited to describe them as if they were on the render
  path. `raster.py` and `field.py` *are* imported and survive. The `box_junction`
  self-test entry is removed from `tests/run_all.py`, so the suite is 62 entries
  rather than 63.
- **The `verification/` evidence tree (346 tracked files, 4.6 MB)** is no longer
  part of the repository. It held eight full copies of `smartcli_core/screen_model.py`
  taken before three separate bug fixes, so a repo-wide search returned
  pre-fix code. It was moved byte-for-byte and nothing was deleted; the sha256
  pins inside it still resolve, because they name files that stayed in the
  repository.

### Documentation
- Colour-degrade and `box_junction` claims across **ten and eleven** documents
  respectively were rewritten to state what the renderer actually does, and then
  the code was cut to match. The modules were briefly documented as
  "standalone, not wired" before that resolution — the intermediate state was
  accurate but described something that then stopped existing.
  > **Erratum (2026-10-01):** this entry shipped as "across **nineteen** and
  > ten documents respectively". The **ten** was right; the **nineteen** was not
  > derivable from anything and has been replaced by the number the delta can
  > actually support. Measured 2026-10-01 over `git diff b0b660c 13985b5`
  > (the release delta), counting documents in which a line matching the
  > degrade family (`degrade|downgrad|truecolor|mono|256`) or the
  > `box_junction` family was added or removed:
  >
  > ```
  > had a degrade-family line touched : 10
  > had a box_junction line touched   : 11
  > union                             : 11
  > ```
  >
  > A sweep of seven patterns × four scopes over the current tree does not
  > yield 19 either (9 docs mention `color_model`, 22 mention "degrade", 26 the
  > union, 17 both "degrade" and "256"), so the original figure was a guess
  > wearing a numeral's clothes. An approximate number in a changelog reads as
  > a precise one, which is why it is corrected in place and dated rather than
  > quietly deleted.
- `CHANGELOG.md` instructed `pip install "smartcli-toolkit[mcp]"`. There is no
  `mcp` extra — `mcp>=1.0,<2` has been a required dependency since 0.2.0 — so
  that command warned and installed nothing extra. The historical entry is kept
  and annotated rather than rewritten.
- `CLAUDE.md` stated the suite "returns 56 entries" and several derived counts
  from it; the live value was 63 (62 after the cut above). Six more count
  families — MCP tool count, knowledge-file count, theme count, the widget
  core/ext split, and two CJK site-page claims no existing pattern could match —
  are now derived from live sources inside `tests/test_doc_counts.py`.

## [0.3.2] - 2026-09-16

### Fixed
- **A partial device reply was never retried.** A reply the runtime could not write in full was reported
  (`io.pending.reply_bytes` / `reply_error`) and then abandoned, so a child blocked on its own answer
  stayed blocked. The unwritten suffix is now retried on a later turn from the ledger -- the same
  suffix, never a re-send from zero -- bounded by an opt-in byte budget (`SMARTCLI_REPLY_RETRY_BYTES`,
  default 0 = off), with the debt still visible in `io.pending`.
- **A peer that stopped reading could hold the daemon's single worker for up to 60 s.** `_reply` now
  runs a non-blocking send loop against two bounds: the 60 s total ceiling (unchanged for a peer that
  is making progress, now tunable via `SMARTCLI_REPLY_TIMEOUT_MS`) and a stall window
  (`SMARTCLI_REPLY_STALL_SECONDS`, default 2 s, 0 disables) that abandons a peer which accepts NOTHING
  for that long. Every accepted byte renews the window, so a slow-but-reading peer keeps the patience it
  had before. The outcome is returned as a receipt (`sent`/`bytes`/`total_bytes`/`reason`).
- **The daemon's reader cap is now an admission limit** rather than a filter on what it lists: work
  beyond the cap is refused explicitly instead of being silently carried.

### Notes
- Verified with the author's own commands (`tests/test_liveness_gaps.py` -> 18 tests OK) and by the full
  aggregator (`python tests/run_all.py` -> 56/56) before the merge; the release commit republishes the
  same tree, so artifact == tag == repository.

## [0.3.1] - 2026-09-16

### Fixed
- **The published 0.3.0 artifact did not match its own tag.** The tag was re-pointed after CI found two
  mypy errors that only exist on the Linux runner (`select.select` handed an `int | None` descriptor;
  the base backend class never declared the budgeted-read hook), so `smartcli_toolkit-0.3.0-py3-none-any.whl`
  on PyPI carried the pre-fix `smartcli_core/pty_backend.py`. 0.3.1 publishes exactly the tagged tree:
  `PtyBackend` now declares `READ_BUDGET_CAPABLE = False` plus `_read_budgeted`/`read_status` (raising
  `ReadBudgetUnsupported`, subclasses override), and the writability wait narrows the descriptor before
  handing it to `select`, reporting `IncompleteWrite(descriptor closed while writing)` if it vanished.
  This is a behaviour-preserving fix, but a release must be the code it names: the artifact, the tag and
  the repository are now the same bytes.
- **The registry publish step is idempotent.** Re-running (or re-pointing) a tag after the version is in
  the MCP Registry returned `400 cannot publish duplicate version` and turned the release-check red,
  while the PyPI step above it already treated the same case as success. The step now skips that one
  message and still fails for every other error.

### Changed
- CHANGELOG 0.3.0 no longer quotes a single writability-wait count as if it were a property of the
  transport: identical 262 144 B fixtures measured 32, 35 and 44 waits. The byte-exact result (delivered
  once, sha256 match) is what the entry stands behind.

## [0.3.0] - 2026-09-16

A trust-and-liveness release for the driving loop: what the runtime *observed*, what it has *not*
read yet*, and what it can *confirm* are now separate, testable facts.

### Fixed
- **A highlighted label was read from the wrong column.** `build_snapshot` sliced the rendered
  string with terminal CELL coordinates, so any wide glyph to the left of a highlighted span shifted
  the text: a three-item Chinese menu reported its selected label as `3` when the highlighted item
  was `保存`. Span text is now aggregated over the cell array. ASCII screens and spans starting at
  column 0 happened to be correct before, which is why the defect survived a green suite.
- **SGR sub-parameters were normalised per read chunk, and wrongly.** `ESC[4:3m` became `4;3` —
  underline *plus italic* — `ESC[38:2::255:0:128m` lost its colour-space slot and produced the wrong
  colour, and `ESC[58:2::1:2:3m` leaked `2/1/2/3` into dim/bold/italic. The rewrite is now a
  streaming filter: state survives `feed()` boundaries, only a complete and definite CSI SGR is
  rewritten, OSC/DCS payloads are never touched, an unterminated CSI is bounded (1024 bytes) and then
  abandoned rather than drawn, and a later valid sequence still works. `38:2::R:G:B` now yields the
  real colour; `4:3` degrades to a plain underline without italic.
- **A short PTY write was reported as success.** `PosixPtyBackend.write` called `os.write` once and
  discarded its return value while the fd is non-blocking, so a long payload could be silently
  truncated. It now keeps an offset, waits for writability on `EAGAIN`, retries the same suffix on
  `EINTR`, honours a deadline, and raises `IncompleteWrite(OSError)` carrying
  `written_bytes`/`total_bytes`/`reason` instead of returning normally. Verified on a real POSIX pty:
  262 144 bytes delivered exactly once (sha256 match), where the previous code returned "success" in
  0 ms with the child never receiving the payload. The wait count is scheduling-dependent -- 32, 35
  and 44 observed across identical runs -- so it is not quoted as a property of the transport.

### Added
- **Byte-budgeted transport.** The built-in backends declare a private budgeted-read capability
  (`_read_budgeted`/`read_status`); `PtySession.pump(max_bytes=...)` accepts a budget and a session
  without the capability is refused *before* any read (`ReadBudgetUnsupported`). A turn that spends
  exactly its budget is reported as `budget_limited`, never as `drained`.
- **`io` evidence on every observation.** `generation`, `read_offset`, `fed_offset`, `pending`
  (`known_payload_bytes`/`readable_now`/`parser_incomplete`/`reply_bytes`/`upstream`), `local_cut`,
  `representation` (`posix_pty_stream` vs `conpty_reconstructed_utf8`), `stream_error`, `basis_origin`
  and the close state. Unknown values are `null`, never `0`, and the CLI/MCP wrappers only forward it
  (`basis_origin=runtime`) instead of filling it in themselves.
- **The daemon services the transport itself.** Every worker iteration runs one byte-bounded I/O turn
  (idle, between requests, and inside a long wait's poll gap), so an agent that asks nothing no longer
  means a child that is not being read. Measured on a real POSIX pty: a child's `ESC[6n` is answered
  in 0.169 s with no client polling and a 256 KiB fixture completes unprompted; with the service turn
  removed the same fixture stalls at 12 288 B exactly as before.
- **`STABLE` now requires a drained observation.** `wait_until_stable`/`wait_ready` accept an optional
  `io_fn`; a budget-limited, unknown, erroring, or mid-sequence observation can no longer be reported
  as a settled screen, and progress made by a poll hook invalidates the quiet candidate.
- **`ScreenModel.stream_incomplete()`** reports whether the byte-to-text path is mid-sequence (the
  streaming filter *or* pyte's incremental UTF-8 decoder), returning `null` rather than a confident
  `False` when it cannot tell.
- **Bounded Windows delivery backlog.** The ConPTY reader stops pulling at a payload high-water mark
  (queue + chunk in hand + held suffix) and resumes below the low mark, waiting on a stop-aware
  condition instead of growing without limit (measured before: 271 307 bytes of unparsed backlog in
  7.5 s with no client polling). Bytes are never dropped; the reader refuses to pull instead.
- **Close protocol.** `close_requested` → `closing` → `closed_confirmed` | `close_unconfirmed` with the
  last progress, on both backends and in the daemon's close reply. A returned native call is never
  reported as a confirmed exit.

### Platform notes
- Windows/ConPTY remains **not** wire-byte-exact: a 1 MiB burst reaches the client as ~12 KB of
  composed stream, and the cap manages only what this runtime has received
  (`source_wire_exact=false`; `delivered_stream_preserved` and `screen_model_consistent` are what the
  tests actually claim).
- Still open and named as such: device-reply progress (a partial reply is best-effort and its failure
  is not yet surfaced), the daemon's reader "cap" that is only a filter, and the 60 s reply stall on
  the single worker.

## [0.2.3] - 2026-08-09

A control-plane concurrency release. The headline is a security fix that v0.2.2
**did not** carry: the daemon's serial accept loop let any local process — with no
credential at all — deny service for ~18s at a time, and `pip install smartcli-toolkit`
still had that. It also removes a second block that was one layer in: a long `wait`
kept a concurrent `snapshot` waiting behind it.

### Fixed
- **One connection could stall the daemon for every other caller.** The accept loop
  was serial with the UNAUTHENTICATED transport read inline, so any local process
  could connect, send bytes with no newline, and head-of-line block every other
  caller — measured at ~18s of denial from nine held connections, repeatable and
  needing no credential. Now the accept thread only accepts, a per-connection reader
  performs the unauthenticated work (read, parse, constant-time token check) so a
  silent peer burns only its own 2s budget, and a single worker thread is the only
  thread that touches the session. Measured after: an authenticated request is served
  in 0.00s under the same attack. A previous release note described this as bounded
  30x but not fixed; it is now fixed.
- **A long wait blocked unrelated fast verbs.** A `wait-regex --timeout-ms 60000`
  occupied the session worker, so a concurrent `snapshot` waited behind it (8.00s,
  measured). `smartcli_core`'s four wait loops and `PtySession`'s six wait methods
  gained an optional `on_poll` hook, invoked in the idle gap **on the waiting
  thread**, so a fast verb is answered without a second thread ever entering the
  session — `PtySession` is not thread-safe (`visual_hash()` clears `screen.dirty`
  as a side effect, `pump()` is read-modify-write, `resize()` mutates four fields in
  sequence). Default `None`, so every existing caller behaves identically. On a live
  PTY: `snapshot` in 0.13s during a 20s `wait-regex`. A second LONG wait still queues
  behind the first — one session owns one PTY child, so that is inherent.
  `resize` is deliberately NOT answered mid-wait: it re-dimensions the pyte screen and
  therefore changes the content hash, which would make a caller blocked in
  `wait-change` conclude its own keystroke had landed.

### Added
- `tests/test_daemon_concurrency.py` — drives the real accept loop against a fake
  session (no PTY, no child process) and locks: an authenticated request is served
  while `listen` backlog + 1 silent peers hold connections; a 200 KB request spanning
  many `recv()` calls still succeeds; auth is still enforced with no screen leak; a
  fast verb is answered during a long wait; and session access provably stays on one
  thread. Suite is 44 entries.
- `tools/mcp_stdio_smoke.py`, run by `docker.yml` against the built image — the check
  an MCP directory performs (start the container with no arguments, speak JSON-RPC).
  The image had shipped with `CMD ["mcp"]` for three releases with no test ever
  running it.

### Changed
- `test_perf_contract` declines to measure timing ceilings when a tracer is attached
  (coverage runs it under one), because the number measured there describes the
  tracer. Raising the ceiling instead would have destroyed the 2000x regression window
  the gate exists to protect.
- `test_doc_counts` gates README's quoted `drive_vim` output against the example's
  `step()` literals, and the four localized READMEs gained the 30-second quickstart
  and the `drive_vim` comparison.

## [0.2.2] - 2026-08-09

A control-plane correctness release. The headline is that **`close` could delete a
live daemon's registry entry**, stranding a real PTY child while the very command
this project tells you to use for confirming cleanliness reported zero sessions.
Everything else here either closes a security bypass or makes a check capable of
failing; there are no new features.

### Fixed
- **`close` after a failed request deleted the registry entry of a LIVE daemon.**
  `_call` turns any transport failure — *including a plain timeout* — into a
  `SystemExit` telling the operator to run `close --id <sid>` "to clean up the stale
  entry", and `close` then unlinked the file unconditionally. But the daemon's accept
  loop is serial, so a busy daemon is indistinguishable from a dead one at the socket,
  and that file is the only store of both the capability token and the pid. The
  documented recovery could therefore leave a live daemon owning a running PTY child
  that was unreachable by protocol (token gone) and unfindable for a manual kill (pid
  gone) — while `close` printed `closed <sid>`, exited 0, and `list` reported zero
  sessions. Since this project's own guidance is to confirm "zero leaked sessions" with
  exactly that `list`, the check would have confirmed a lie. Death is now proven before
  deletion (`os.kill(pid, 0)` on POSIX, `OpenProcess` + `GetExitCodeProcess` on
  Windows, where signal 0 does not exist); `close` refuses and exits 1 with the pid, and
  the new `--force` overrides it while saying in its help what that costs.
- **`--env` could re-inject the session token on Windows.** The control-plane guard was
  `key.startswith("SMARTCLI_TUI_")` — an exact-case check — while Windows environment
  names are case-insensitive and CPython upcases keys on assignment. So
  `--env smartcli_tui_token=…` passed validation and `os.environ.update()` installed it
  **as `SMARTCLI_TUI_TOKEN`** in the driven child: precisely the capability the daemon
  pops so a child cannot control its own session. Now compared uppercased
  unconditionally, with the deny-list widened to `SMARTCLI_ROOT`,
  `SMARTCLI_MAX_SESSIONS` and `SMARTCLI_AUTO_INSTALL`. Your own variable names are
  unaffected.
- **An unauthenticated peer could head-of-line block the daemon for 60s per
  connection.** `conn.settimeout(60.0)` was set *before* the token check, so any local
  process could connect, send bytes with no newline, and stall every other caller with
  no credential at all; with `listen(8)`, nine such connections starve the owner. The
  budget is now split — 2s pre-auth, re-armed against a **fixed deadline** so a peer
  dribbling bytes cannot renew it, and 60s only for an authenticated caller's reply.
  **Measured: nine held connections went from 540s to 18s. That is a 30× reduction and
  NOT a fix** — the residual is inherent to the serial accept loop. Per-connection
  threading is the real answer and is deliberately not attempted here, because
  `PtySession` is not thread-safe; `SECURITY.md` now documents the residual instead of
  claiming the bound prevents it.
- **A non-dict JSON request was answered with an interpreter exception, pre-auth.**
  `[1,2,3]` reached the handler and died on `req.get()`; `AttributeError` was not in the
  connection guard's tuple, so an unauthenticated peer received
  `{"error": "AttributeError: …"}` with no `ok` field, unlike every other reply on the
  socket. Rejected explicitly now, before dispatch.
- **`examples/drive_vim.py` sent five keystrokes blind and did not set `TERM`.** The
  mode changes (`Escape`, `G`, `o`) were issued back to back with nothing between them —
  the blind send this project exists to argue against — so under load the keystrokes
  were swallowed and nothing was inserted. It now confirms `-- INSERT --` before typing,
  which proves both `G` and `o` landed. And without a `TERM` vim never enters the
  alternate screen nor saves the file, so two of the six steps failed for the absence of
  an environment variable rather than for anything in the code; it is set explicitly now.

### Changed
- **`tests/run_all.py` no longer reports success for a gate that was deleted.** 29 of 43
  entries were `optional=True`, including 20 committed deterministic gates, so renaming
  or removing any of them was a green SKIP — while the runner is documented as
  pass-or-fail. A missing file that git tracks is now a FAIL regardless of the flag,
  which is derived rather than hand-maintained and so covers a new gate the moment it is
  committed. Entries that depend on an external binary (tmux, vim, less) still skip
  themselves internally, so a green run on a host lacking those covers less.
- **`run_all.py` retains and prints child output on failure** (last 40 lines), and
  surfaces internal `SKIP:` lines even on a PASS. Previously a suite failure was
  reportable only as an exit code and had to be re-run standalone — exactly the case
  where an order- or load-dependent failure does not reproduce.
- **Anti-drift gates that could not fail, fixed.** `test_fx_contract`'s exact-width
  contract was gated on a predicate that evaluated the very condition it asserts, so any
  effect *violating* it was reclassified "sparse" and passed; the classification is now
  a frozen 24-name set with a second check so it cannot rot in either direction, and
  skipped contracts are no longer counted as passes (the summary reads
  `174/174 passed, 6 skipped`, where "150/150" had included six checks that never ran).
  `test_doc_counts` exempted its own authoritative counts line by inferring intent from
  nearby words — exemption is now an explicit `doc-counts:ignore` marker — and it now
  gates the recipe count it had only been printing. The dependency gate's Homebrew
  half ran a pip-shaped regex over a Ruby formula and could not match under any
  circumstances; each draft is now parsed in its own syntax.
- **`tests/_tmux_launcher_probe.py` read the new pane the instant the launcher
  returned.** The single-effect branch ends in `exec tmux split-window`, which returns
  when the pane *exists* — measured, the first frame arrives ~0.5s later — so it
  sampled a legitimately blank screen. It now polls for the condition with a bound. It
  also sets `TERM`, without which tmux refuses to attach a client and two more checks
  failed for a rig reason.

### Notes
- No API or behaviour change for library users beyond `close`'s new refusal (and the
  `--force` escape hatch). `smartcli_core`'s public surface is unchanged.
- `tests/run_all.py` is 43/43 on macOS with no FAIL, no SKIP and no rerun.

## [0.2.1] - 2026-08-06

A perception-correctness release. The headline is not a feature: **an upgrade of
`pyte` alone could have blanked the primary screen for every 0.2.0 user**, and
this release defuses that before it ships upstream. Everything else is the
alternate-screen work reaching the surfaces an agent actually reads, plus five
more measured emulation fixes.

### Fixed
- **Two dependency timebombs, defused by capability detection rather than a
  version pin.** `pyte>=0.8.1` is an open range in both `requirements.txt` and
  `pyproject.toml`, so the day upstream ships its own alternate screen
  ([selectel/pyte#212](https://github.com/selectel/pyte/pull/212), which this
  project authored), subclass *and* base class would both switch — restoring a
  BLANK primary screen on every full-screen program exit. Measured: `['', '', '']`.
  The second is `delete_characters` widening DCH over a wide glyph; against a pyte
  that does the same, `中x` + CR + DCH went from `"x"` to `""`, silently eating a
  character. Both now ask the installed pyte what it can do (`_PYTE_HAS_ALT` via
  `hasattr`, `_PYTE_DCH_HANDLES_WIDE` via a one-shot behavioural probe). A cap
  would have kept users off the upstream fix forever and needed revising every
  release. Verified under BOTH stock 0.8.2 and a patched checkout, because a
  one-sided test cannot distinguish "correct" from "the branch that happens to run
  here".
- **`CUD` (cursor down) was missing its DECSTBM override.** `index()` and
  `cursor_up()` were overridden for exactly this defect class; their mirror was
  not, so from below a scroll region `ESC[3;6r ESC[8;1H ESC[1B` landed on row 6
  where tmux and GNU screen both give row 9. Found by asking why the third
  override was absent — a gap a generative fuzzer cannot surface, because it
  generates sequences, not absences.
- **`DL` (delete lines) left the rows it vacated populated** instead of blanking
  them.
- **Resizing while on the alternate screen** clipped the saved primary screen
  correctly, restored the pen along with the cursor, and left the alternate screen
  on RIS.
- **Mode 1048 no longer collides with 1049's save slot.** Adding 1048 initially
  routed it through the same `_alt_savepoint` as 1049, reintroducing the defect
  the dedicated slot was created for one commit earlier.
- **The MCP `snapshot` tool silently dropped `alt_screen`.** The daemon has always
  sent it and the CLI has always printed it, so MCP clients — the surface this
  project promotes hardest — were the only ones that could not tell whether a
  full-screen program owned the screen. That is precisely the blindness the
  alternate-screen work exists to remove.
- **The mypy gate was checking a state that does not exist.** CI installed only
  `ruff` and `mypy`, so `pyte` was absent, `ignore_missing_imports` degraded
  `pyte.Screen` to `Any`, and a correct `type: ignore` was reported as unused
  while two genuine errors present since 0.2.0 went unseen. The gate now installs
  the runtime dependencies and is mutation-verified to still bite.
- `examples/drive_vim.py` runs from a source checkout, not only an install, and
  the driven test fixtures no longer `import msvcrt` unconditionally — that alone
  was four of the suite's failures on POSIX.

### Added
- **Private mode 1048** (cursor save/restore without the buffer switch), with its
  weaker evidence level stated in the code: xterm defines it, but neither
  reference emulator implements it, so there is no ground truth to check against.
- **`alt_screen` on every surface an agent reads** — `ScreenModel`, `Snapshot`,
  the `to_text()` header (it leads the flags, because it changes what an action
  MEANS), the JSON hints, and every drive-tui daemon reply. Previously reachable
  only by poking the underlying pyte object.
- **`tui.py resize`** — the daemon and MCP had supported resize since the control
  plane was hardened; the CLI had no verb. A rejected size returns an error and
  leaves the session alive.
- `tests/test_terminal_fidelity.py` locks, including DECCOLM against the alternate
  screen, and a cross-platform `getwch()` (`tests/_kbd.py`) that enters raw mode
  once rather than per keystroke — otherwise an `ESC [ A` gets split across three
  separate raw-mode entries.
- `RESEARCH-PROMPTS.md` — the calibrated research anchors, each recording what a
  good answer would actually change in the backlog.
- CLI coverage for `resize` in `tests/_tui_cli_probe.py`, including the check that
  a *rejected* size leaves the session alive. `_validate_size` raises `SystemExit`,
  a `BaseException` that would otherwise pass straight through the daemon's
  per-connection `except Exception` and tear the session down; nothing had pinned
  that from the CLI side.

### Fixed after an adversarial self-review
The release was reviewed before tagging. Five real defects came back, all
introduced by this release's own work, and all fixed here — **four found by
independent adversarial agents, and the last (the version contradictions) found by
reading back over the release commit rather than by any agent or gate**.

To be precise about what that does and does not claim: the *defects* were found
independently, but the *fixes written in response* were verified by the author only.
One of them touches `smartcli_core`, whose policy requires independent adversarial
review before a change ships. That review happened AFTER the tag, not before, so the
policy was not met for this release. It has since been run and the fix held up; the
gap is recorded rather than smoothed over.
- **The lint-gate fix would have re-broken the gate from the other direction.** The
  `type: ignore[misc]` on `super().alternate_screen` is correct only while pyte
  *lacks* the attribute; the day pyte ships it, `warn_unused_ignores` fails on an
  ignore that has become unused. Reproduced by injecting the attribute. Replaced
  with `getattr(super(), "alternate_screen", False)`, which needs no ignore in
  either state — a version-dependent ignore would have needed revising on the very
  release that makes the capability check unnecessary.
- **`resize` was invisible in `tui.py --help`**: the subparser metavar is a
  hand-maintained string and the new verb was never added to it.
- **A rejected resize printed `error: error: ...`** — the daemon stored
  `_validate_size`'s already-prefixed message while every other daemon reply
  stores a bare one for `_call` to prefix once.
- **The HANDOFF continuation prompt listed six portable pyte defects including
  IL/DL cursor column.** It is five, and IL/DL is explicitly excluded — filing it
  upstream would have been rejected, since pyte matches the standard there and
  this project is the deviation. That prompt is what a fresh session pastes and
  follows, so the error was one step from becoming a bad upstream patch.
- **Two version contradictions inside HANDOFF.md** — a `VERSION = 0.2.0` line nine
  lines below the 0.2.1 banner, and a "read this first" pointer still routing to
  work from two rounds earlier. The ten-site version gate cannot see prose.

### Changed
- `tests/run_all.py` is **43/43 on macOS**, the first full green on this host. The
  four prior failures were platform gaps in test fixtures, not product bugs — and
  with four known failures a genuine regression was indistinguishable from the
  noise floor.
- Documented as a deliberate CHOICE rather than a bug: **IL/DL keep the cursor
  column.** An independent re-check found pyte matches xterm, vte and the DEC VT
  reference here; tmux, GNU screen, urxvt, konsole and linuxvc keep the column as
  this project does. Five implementations against two, so the behaviour stays —
  but it must not be upstreamed, and the docstring that had asserted "real
  terminals keep the column" now records the full split.
- **GitHub Actions pins brought current** — 27 pins across 9 workflows
  (`checkout` v4→v7, `setup-python` v5→v7, `deploy-pages` v4→v5,
  `configure-pages` v5→v6, `upload-pages-artifact` v3→v5, `login-action` v3→v4,
  `codeql-action` v3→v4), clearing a seven-PR Dependabot backlog and the Node 20
  deprecation warning on every run. The breaking changes were read rather than
  assumed: `checkout` v7 blocks fork-PR checkout under `pull_request_target` /
  `workflow_run` and `setup-python` v7 removed the `pip-install` input — this repo
  uses neither. `mkdocs-material` docs-build floor raised to 9.7.7.

## [0.2.0] - 2026-07-27

Security hardening of the drive-tui control plane, an installable MCP surface,
and — from a differential-testing campaign against real terminals — **twelve
screen-emulation bugs fixed**, including one that made every full-screen TUI
unreadable. See HANDOFF §10 for the full arc.

### Added
- Installable `smartcli-tui`, `smartcli-mcp`, and registry-compatible
  `smartcli-toolkit` console commands; the wheel now includes the drive/MCP
  implementation instead of shipping only `smartcli_core`.
- `cwd` and repeated `KEY=VALUE` environment controls for persistent sessions,
  machine-readable start/list/close output, and structured MCP snapshots.
- `visual_hash` + `wait_visual_change` across core, daemon, CLI, one-shot steps,
  and MCP for attribute-only selection and cursor movement.
- **Alternate screen buffer support** (modes 1049/1047/47) with
  `ScreenModel.screen.alt_screen`. pyte implements none of these, so until now a
  full-screen program (vim, less, htop) painted its alternate screen on top of
  the main one and never restored it — an agent read a merged, impossible screen.
- **SGR sub-parameter tolerance** (ITU-T T.416 `:` syntax, e.g. `ESC[4:3m`,
  `ESC[38:2::R:G:Bm`), which pyte's parser aborted on, drawing the remainder of
  the sequence onto the grid as literal text. Neovim, kitty and delta emit it.
- Differential test suite against real terminals: `_diff_tmux_pyte.py` (35
  curated cases vs tmux), `_diff_two_refs.py` (tmux AND GNU screen; ground truth
  only where both agree), `_diff_fuzz_tmux.py` (generative VT fuzz),
  `_tmux_launcher_probe.py`, plus deterministic locks in
  `test_terminal_fidelity.py`.
- `test_perf_contract.py` — the first performance test in the suite — and
  `test_readiness_properties.py` (Hypothesis invariants for the wait primitives).
- `test_version_sync.py`, a ten-site version anti-drift gate; widget-count and
  dev-box-path gates in `test_doc_counts.py`.
- Cross-platform package/MCP smoke jobs and Python 3.10/3.14 CI boundaries.
- OIDC MCP Registry publishing after a successful PyPI tag release.

### Fixed
- Explicit `wait_change` baseline hashes are integers end to end; CLI/MCP calls
  no longer report an immediate false change because of a string/int mismatch.
- Session ids can no longer traverse outside the registry directory, registry
  writes refuse symlinks on POSIX, and controlled children no longer inherit
  the daemon capability token.
- Detached session count is bounded (8 by default, configurable up to 128),
  stale close actually removes its registry entry, and MCP close is idempotent.
- An out-of-range `resize` no longer kills the daemon and its live session
  (`SystemExit` escaped the per-connection guard).
- **Screen-emulation fidelity**, each divergence measured against real tmux and,
  where it could arbitrate, GNU screen: IL/DL no longer home the cursor column;
  IL with count > 1 no longer leaves buffer holes that make a later DL delete the
  wrong row; half-overwriting a wide glyph blanks it instead of dropping the
  incoming character; DCH removes both cells of a wide glyph; NEL returns to
  column 0; a cursor outside a DECSTBM region is neither dragged into it nor
  clamped by it; a two-column glyph with one column left wraps whole; an
  overwritten wide base leaves no orphaned stub; and a zero-width joiner or
  variation selector no longer truncates the rest of the write (`"MENU ♀️
  Settings  Quit"` used to be perceived as `"MENU ♀"`).
- `visual_hash` is incremental — 16.6 ms → 0.008 ms per idle poll on a 300x100
  screen, where it previously consumed 55% of the 30 ms polling budget.
- `fx-popup.sh` refuses cleanly when no tmux client is attached instead of
  leaking tmux's `no current client` with a non-zero exit.
- Real-session probes use the running Python interpreter with platform-correct
  quoting instead of assuming a `python` command exists on PATH (not true on
  current macOS installations).

### Changed
- Python 3.10 is now the supported floor because the packaged MCP surface uses
  modern type syntax; the MCP SDK is a required package dependency so `uvx`
  launch from the official MCP Registry works without extra flags.

## [0.1.8] - 2026-07-15

Two capability additions and a benchmark adapter, each with an independent
adversarial review pass. Closes the last of the pexpect feature gap, adds a true
graphics protocol, and makes "drives TUIs" a runnable Terminal-Bench score.

### Added
- **`wait_any` — pexpect `expect([...])` multi-marker wait** (smartcli_core, made
  under the DO-NOT-MODIFY exception: real-run-path + independent adversarial review
  + full-suite green). Race several regexes and learn WHICH matched first: returns
  `(index, snapshot)`, `-1` on timeout, earliest-in-list wins a same-poll tie, empty
  list short-circuits. In `readiness.py` + `PtySession.wait_any` + the drive-tui
  daemon action, CLI (`wait-any`, `--pattern`/`--stdin`), one-shot run step, and MCP
  tool. `tests/test_wait_any.py` (mutation-verified); live-PTY confirmed.
- **Sixel graphics output** (tui-ui, pure addition). `ui/sixel.py` encodes an RGB
  pixel grid — including a `SubcellRaster.px` buffer via `raster_to_sixel` — to a
  Sixel DCS string for terminals that support it (Windows Terminal >=1.22, xterm,
  WezTerm, mlterm): band-based encoding, 6x6x6 cube quantization, RLE, transparent
  zero-bits, `char=0x3F+mask` (bit0=top), 0..100 color scaling. Plus `supports_sixel`
  (DA1 probe) and `python -m ui sixel [image] [--probe]`. Wire format locked to the
  VT330/340 spec by `tests/test_sixel.py` (incl. the DEC "HI" bit-math + a round-trip
  decode), mutation-verified, adversarially reviewed. The sub-cell glyph path
  (half/quad/sextant/braille) still works everywhere; sixel is the upgrade where
  available.
- **Terminal-Bench agent adapter** (`smartcli_tbench/`, not shipped in the wheel).
  A classic-`terminal-bench` `BaseAgent` that drives the harness's tmux session with
  SmartCLI's perceive→decide→act→wait→confirm loop and its wait primitives
  reimplemented over `capture_pane()` — the reliability the stock fire-and-forget
  `naive` agent lacks. `driver.py`/`loop.py` are pure and unit-tested without Docker/
  LLM (`tests/test_tbench_adapter.py`, adversarially reviewed — a stale-screen
  `min_wait` guard was added from that review); `agent.py` imports terminal-bench
  lazily. New `.github/workflows/bench.yml` runs the scored subset on CI ubuntu-latest
  (oracle smoke test + `SmartCliAgent`, gated on an LLM API-key secret).

### Changed
- CI gains deterministic gates for `test_wait_any`, `test_sixel`, and
  `test_tbench_adapter`; all three added to `run_all.py`. drive-tui + tui-ui SKILL.md
  document the new verbs/commands. (Stale "19 effects" CI comments corrected to 30.)

## [0.1.7] - 2026-07-15

The last two "knowledge → effect" ports, an MCP Registry listing, and a
docs/website accuracy pass. Catalog grows to 30 effects.

### Added
- **Two new fx effects** (30 total): `spectrum_bars` — an audio-style spectrum
  meter over a synthesized signal, faithful to cava's pipeline (log-spaced bins,
  gravity-fall + integral smoothing, eighth-block `U+2581..U+2588` sub-cell
  vertical resolution; aliases `spectrum`/`bars`) — and `cbonsai` — a procedural
  ASCII bonsai grown by a stochastic branching turtle (the cbonsai recursion:
  lifeStart 32, multiplier 5, five branch types, cooldown-gated side shoots). The
  whole tree is generated once with a seeded RNG as an ordered draw-event list and
  each frame reveals the "grown" prefix, so it animates and is fully deterministic.
  Both ship as pure frame producers and pass the frame contract at all sizes.
- **Official MCP Registry listing** — `io.github.dwgx/smartcli` is now published
  on `registry.modelcontextprotocol.io`, so MCP clients (Claude / Cursor / VS Code)
  and aggregators (Smithery / Glama / MCP.so) auto-discover the drive-tui server.

### Changed
- Docs + showcase site reconciled to the 30-effect catalog (READMEs in all five
  languages, both SKILL/USAGE, the site's effect-count stat across all five
  localized pages, and the anti-drift `test_doc_counts` gate).
- `server.json` `description` trimmed to the registry's 100-char limit.
- `.gitattributes` now marks the `docs/site` sources (HTML/JS/CSS) as
  `linguist-detectable` and the localized translations / vendored core as
  generated/vendored, so GitHub's language bar reflects the real HTML+JS+Python
  mix instead of reading ~99% Python.

## [0.1.6] - 2026-07-15

Six new "god-tier" effects, two new widgets, a rendering-quality pass, a new
drive-tui wait primitive, and a website upgrade — all through a two-reviewer
code-review pass that caught and fixed a high-severity bug before release.

### Added
- **Six new fx effects** (28 total): three noise-composition **field** effects —
  `flames` (rising domain-warped heat convection + physical black-body color),
  `water` (sum-of-sines swell + caustic net), `nebula` (domain-warped gas
  filaments + multi-color mixing + stars) — and three **TTE-style text intros**
  — `text_flyin`, `text_converge`, `text_decrypt` — built on a new TextEffect
  base and a shared `easing.py` (14 canonical easings). Fractal effects
  (`julia`/`mandelbrot`) gained smooth/continuous iteration coloring; `perlin`
  gained fBm. Noise techniques (domain warping, ridged noise, black-body ramp)
  live in a shared `_noiselib`.
- **Two new tui-ui widgets** (17 total): `FuzzyFilterList` (fzf-style subsequence
  fuzzy filter with match highlighting) and `PreviewPane` (its companion content
  preview).
- **`sextant` sub-cell blitter** (2x3, +50% vertical resolution over quad) and
  **OKLab perceptual color distance** for color clustering (chafa's quality
  lever).
- **`wait_change`** in drive-tui (CLI / MCP / daemon): block until the screen
  content changes — the precise "did my action land?" primitive.
- Website playground shows a copy-able `python -m fx play <effect>` command.

### Fixed
- **sextant glyph mapping** was wrong for 42/62 masks (the U+1FB00 block omits
  the left/right-column patterns, which are the half blocks U+258C/U+2590) —
  found in review, rebuilt from the Unicode names, now asserted exactly.
- OKLab color distance no longer crashes on out-of-range/negative channels.
- `perlin` noise uses `math.floor` (not truncation), fixing negative-coordinate
  seams the field effects hit constantly.

## [0.1.5] - 2026-07-15

Three new effects, a device-query fix in the core, diagnostics, width knobs, MCP
tool annotations, and a knowledge-graph expansion.

### Added
- **Three new fx effects** (22 total), implemented from the knowledge-graph
  formulas: `julia` (animated escape-time fractal with **smooth/continuous
  iteration coloring** — no concentric banding), `mandelbrot` (infinite zoom,
  same smooth coloring), and `perlin` (Ken Perlin's improved gradient noise as a
  flowing **fBm** field of 4 octaves).
- **`python -m smartcli_core`** — environment diagnostics (OS, Python, terminal,
  PTY backend, dependency versions) to paste into bug reports.
- **MCP server** now declares standard tool annotations (readOnly / destructive
  / idempotent / open-world) on all 11 tools, and a `server.json` is prepared for
  listing on the official MCP Registry.
- **Knowledge graph**: notes for `solarsystem` and `sphere`, plus a
  `choosing-an-effect` decision guide that maps "I want to show X" to a
  direction, formula, and shipped effect.
- `char_width` / `width` gain optional `unicode_version` and `ambiguous_wide`
  knobs (defaults unchanged) so callers can pin width to their terminal.

### Fixed
- **`smartcli_core` device queries (DSR-CPR / DA)** — a driven program that
  emitted `ESC[6n` / `ESC[c` and synchronously waited for the reply could stall
  or degrade, because nothing answered. `PtySession.pump()` now writes back the
  reply pyte generates from its own cursor/attr state (touched the core under the
  DO-NOT-MODIFY exception, with adversarial review + full-suite verification).
- **`fx random`** no longer picks an effect that renders statically under its
  defaults (`text3d`), which was the source of the `verify_fx` `random` flake.
- Read-the-Docs site: repo-relative links (the README language switcher) are
  rewritten to absolute GitHub URLs, so localized-README links no longer 404.

## [0.1.4] - 2026-07-15

New MCP server (the biggest adoption lever in the backlog), a real fx bug fix, a
golden-frame regression suite for tui-ui, multi-process coverage, and the
contributor onramp.

### Added
- **MCP server over the drive-tui daemon** (`skills/drive-tui/scripts/mcp_server.py`;
  it shipped behind a `smartcli-toolkit[mcp]` extra, **since removed** — `mcp` is a
  required dependency from v0.2.0 on, so plain `pip install smartcli-toolkit` is the
  install command and the `[mcp]` extra no longer resolves). Exposes the daemon's
  verb surface as 11
  MCP tools (`start`, `list_sessions`, `snapshot`, `send_text`, `send_line`,
  `send_keys`, `wait_regex`, `wait_ready`, `alive`, `resize`, `close`) so any MCP
  client can drive interactive TUIs. It reuses the CLI's client layer, so the
  per-session capability token is attached automatically and no verb is exposed
  unauthenticated. Covered end-to-end by `tests/_mcp_probe.py`.
- **Golden-frame snapshot regression for tui-ui** (`tests/test_golden_frames.py`
  + `tests/golden/`). Every widget is rendered to a deterministic frame and
  diffed against a committed baseline (`--update` to regenerate); locks all 15
  widgets against silent visual regressions.
- **Multi-process test coverage** (`tools/coverage_run.py` + `.coveragerc` +
  `sitecustomize.py`) over the script-style suite, wired into CI with a Codecov
  upload. Measures the deterministic, instrument-friendly gates.
- **Contributor onramp**: `CONTRIBUTING.md`, `SECURITY.md`, and a Read-the-Docs
  config (`.readthedocs.yaml` + `tools/build_docs.py`) that assembles the mkdocs
  site from the canonical sources.

### Fixed
- **`fx random` could pick a static effect** (`text3d`, whose `animated` class
  flag is True but whose `is_animated(defaults)` is False). It now selects only
  effects that actually animate under their defaults — matching the "play a
  random effect" promise and removing the `verify_fx` `random --seconds 1` flake
  at its source. `verify_fx`'s assertion was also broadened as defense-in-depth.

## [0.1.3] - 2026-07-14

Documentation accuracy, anti-drift hardening, and test-suite coverage. No
`smartcli_core` code changes — the published package is byte-for-byte 0.1.2; this
release re-cuts it alongside the repo-consistency and doc fixes below.

### Fixed
- **Localized READMEs drifted from the code.** The four i18n READMEs
  (`zh-Hans` / `zh-Hant` / `ja` / `ko`) stated **18 effects** and omitted
  `solarsystem` in their feature paragraphs while the English README and their own
  quick-start/tree already said 19. Corrected all four to **19 effects** with
  `solarsystem` listed.
- **Anti-drift gate was blind to CJK phrasings.** `tests/test_doc_counts.py` only
  matched the English `"N effects"` form, so the localized drift above slipped
  past it. It now also matches the CJK unit phrasings
  (`种效果` / `種效果` / `種のエフェクト` / `개 이펙트`) and forces UTF-8 stdout so it
  runs standalone on a legacy Windows codepage. Mutation-verified: it fails on the
  pre-fix READMEs and passes after.

### Added
- `tests/_tui_cli_probe.py` (drive-tui CLI end-to-end + per-session token auth) is
  now wired into the unified `tests/run_all.py` runner.

### Changed
- Website hero de-branded: the static `demo.svg` animation and the `app.js`
  carousel scenario now use a generic agent CLI placeholder instead of a specific
  vendor's branding (the three-scenario carousel is unchanged).
- `HANDOFF.md` / `NEXT-STEPS.md` reconciled with the shipped state: 3-OS CI matrix
  (was Windows-only), 8 workflows, video proof reels, and the daemon-hardening work.

## [0.1.2] - 2026-07-11

Correctness fixes found by a deep review + mutation-testing pass, each with a
repro and a regression-lock test (all independently re-verified for drift).

### Fixed
- **`smartcli_core` readiness (#1)** — `wait_ready`/`wait_until_stable` could
  declare STABLE on a never-painted blank screen during a startup quiet-gap.
  Added an optional `blank_hash` gate (default off = old behavior); `PtySession`
  passes its blank baseline so a blank+no-output screen TIMEOUTs instead of
  falsely settling, while a drawn static screen still settles.
- **`smartcli_core` docs (#2)** — the quickstart marker `r">>> $"` can never
  match (pyte space-pads lines); examples now use unanchored `r">>> "`.
- **`smartcli_core` PTY backend (#4)** — `WinptyBackend.spawn` now resets its
  queue/EOF/reader so a re-used backend can't inherit a stale EOF sentinel or a
  latched `_eof`.
- **Degenerate-input crashes** in skill code: `field.Ripple` (wavelength 0,
  falloff 0, empty palette), `SliderTrack` (empty positions list),
  `BrailleChart` (non-finite series values), and `fx` `Param` int coercion
  (zero-padded `08`/`010` and `±`-signed based literals now parse; clean error
  message otherwise).

### Added
- Regression-lock tests: `test_readiness.py` (blank-gate + false-green hardening),
  `test_degenerate_inputs.py`, `test_fx_contract.py` (exact fx frame contract,
  18×6), a `box_junction` self-test, and a unified `tests/run_all.py` runner.

## [0.1.1] - 2026-07-11

Test coverage, release maturity, and metadata. No `smartcli_core` code changes.

### Added
- **Test coverage** for previously-uncovered paths: live end-to-end driving of the
  pager / form / wizard recipes (`_drive_probe6.py` + fixtures), deterministic
  virtual-clock unit tests for the readiness TIMEOUT/STABLE/MARKER/late-flush/min_wait
  paths (`test_readiness.py`), drive-tui CLI + per-session token-auth E2E
  (`_tui_cli_probe.py`), a `box_junction` engine self-test, and a unified
  `tests/run_all.py` runner.
- **PyPI Trusted Publishing (OIDC)** workflow (`.github/workflows/publish.yml`) —
  tokenless releases on tag push.
- **Packaging metadata** — trove classifiers, keywords, and `[project.urls]`.

### Changed
- Skill `SKILL.md` descriptions trimmed to ≤500 chars, made agent-neutral, and
  YAML-hardened for marketplace listings.

## [0.1.0] - 2026-07-08

Initial public release.

### Added
- **Shared core (`smartcli_core`)** — a pluggable PTY backend + `pyte` screen model +
  semantic snapshot + readiness sync (`pty_backend / screen_model / snapshot /
  readiness / session`). Not tmux-bound: Windows uses ConPTY via `pywinpty`, POSIX uses
  the stdlib `pty` backend. Exposes `PtySession` as the importable entry point.
- **`cmd-art` skill** — a frame-producer effect engine (`Effect` ABC + `@register`
  auto-discovery) with **18 effects** and **8 themes**, driven by `python -m fx`
  (`list / show / play / gallery / random`). `play` is bounded by default and restores
  the terminal via try/finally.
- **`drive-tui` skill** — drives interactive terminal programs through a PTY via a
  perceive → decide → act → wait → confirm loop. Thin CLI (`scripts/tui.py`) with a
  persistent detached session and a one-shot `run` mode, plus an importable pattern
  library of **8 recipes** (repl, menu_select, pager, search_filter, confirm, form,
  progress, wizard) with fault-isolated discovery.
- **`tui-ui` skill** — a web-like, cell-accurate terminal layout engine emitting
  tmux-safe ANSI frames (SGR + newlines only), with **15 widgets** and an engine of four
  primitives (`field.py`, `raster.py`, `box_junction.py`, `color_model.py`). Correct
  CJK/emoji/ZWJ cell-width handling so columns never desync. *(0.1.0 record, kept as
  written: the "15 widgets" was right then and is 17 now. Annotated 2026-10-01 —
  of the four primitives named above, only `field.py` and `raster.py` are on the
  render path; `box_junction.py` and `color_model.py` ship unwired, so "engine of
  four primitives" overstates what the renderer composes.)*
- **Knowledge graph (`knowledge/`)** — a 122-note wiki-link graph of measured rendering
  formulas, ANSI sequences, and constants, each note sourced and cross-linked; entry
  point `knowledge/INDEX.md`.
- **Screenshot harness (`tools/screenshot/`)** — renders terminal output through `pyte`
  and Pillow into PNG files for smoke testing, honestly labelled `pyte-simulation`.
- **AGENTCLI harness (`tools/agentcli/`)** — validates PTY control of agent-like CLIs
  against a local mock (no API keys) with an optional `--external` probe of installed
  agent CLIs.
- **Packaging metadata** — `pyproject.toml` (installs the `smartcli_core` package),
  `requirements.txt` (required deps), and `requirements-optional.txt` /
  `[art] [image] [width] [all]` extras with graceful stdlib fallbacks.
- **MIT license** and project documentation (`README.md`, `README-USAGE.md`).

[0.1.0]: https://keepachangelog.com/en/1.1.0/
