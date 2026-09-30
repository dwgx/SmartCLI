# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for a
vulnerability.

- Preferred: use GitHub's **[Report a vulnerability](https://github.com/dwgx/SmartCLI/security/advisories/new)**
  (Security → Advisories) to open a private advisory.
- Include: what you found, how to reproduce it, the affected version
  (`pip show smartcli-toolkit` or the git commit), and the impact you see.

You can expect an acknowledgement and an initial assessment. If the report is
confirmed, a fix and a coordinated disclosure will follow.

## Scope — what to look at

SmartCLI drives real terminal programs through a PTY, so the security-relevant
surface is narrow but real:

- **The `drive-tui` session daemon.** `scripts/tui.py start` spawns a detached
  daemon that binds **`127.0.0.1` only** (no external network surface) and owns a
  live child process. Every request must carry a **per-session capability token**
  (`secrets.token_hex(16)`), checked with a constant-time compare
  (`hmac.compare_digest`) before any action runs. The token is passed to the
  daemon via an environment variable (never argv, which is world-visible in
  `ps`/Task Manager) and persisted in a per-session registry file whose
  protection is per-platform and has to be stated per platform. On POSIX the
  file is created `0600` inside a `0700` directory. On Windows those mode bits
  are inert — the `0o600` passed to `os.open` buys no POSIX mode there, and the
  only `chmod` in the module is the `0o700` applied to the *directory*, on the
  POSIX branch — so nothing about a mode bit can be the control doing the work.
  What does the work is an **explicit DACL** that SmartCLI sets on the registry
  directory itself and then **reads back**: exactly three trustees, this
  account, `NT AUTHORITY\SYSTEM` and `BUILTIN\Administrators`, each with full
  control and inheritable, the DACL set `PROTECTED` so nothing is pushed onto
  the directory from its parent. The directory moved off `%TEMP%` to
  `%USERPROFILE%\.smartcli\sessions` to get there: a fresh child of the user
  profile inherits only the profile's own SDDL, and a fresh child of the temp
  directory did not — measured on the Windows dev host with `icacls`, a
  registry directory created under `%TEMP%` carried ten trustees, seven of them
  granted Modify, one of them a local agent-sandbox group. Set but unverified
  would still be a claim, so the DACL is **read back** on every write, on the
  registry directory *and* on each registry file, and its ACEs are walked; if it
  cannot be established, no capability token is written, the file is removed
  rather than left behind, and the command exits with a refusal naming the path
  and the `icacls` to run. A false "still permissive" costs the user one
  command; a false "private" hands a stranger control of a live child process,
  so the unproven case is the refused one. The walk is **fail-closed by
  classification, not by enumeration**: the ACE types that can grant are listed
  in full (0x00 allow, 0x04 allow-compound, 0x05 allow-object, 0x09
  allow-callback, 0x0B allow-callback-object), only a plain
  `ACCESS_ALLOWED_ACE` is one this build can read a trustee out of, and
  anything that is neither a listed grant nor a listed non-grant (0x01/0x02/
  0x03/0x06/0x07/0x08/0x0A/0x0C/0x0D — denials, audits, alarms) ends the walk
  in a refusal. That direction is the fix for a defect that was measured here:
  0x09 was filed as inert, and a DACL whose foreign grant was an
  `ACCESS_ALLOWED_CALLBACK_ACE` read back as PRIVATE while `icacls` showed
  `BUILTIN\Users:(DE,Rc,WDAC,WO,S,...)` — WRITE_DAC, WRITE_OWNER and DELETE for
  a stranger. Both facts are gated in `tests/test_drive_security.py`, which
  builds that DACL, measures the refusal, and re-introduces the old
  classification to prove the refusal is the classification's doing.
  The same DACL is set explicitly on each registry file — and the file is
  **verified** too, not merely set: the file is the object that holds the token,
  so a directory-only read-back left the secret the one thing checked on the way
  in only. What lands inside the directory is a fact about that call rather than
  a consequence of a token default nobody chose.
  **Head-of-line denial of service: FIXED in v0.2.3 (2026-08-09).** The accept loop used to be serial with the unauthenticated transport
  read inline, so any local process could connect, send no newline, and block every
  other caller — measured at ~18s of denial from nine held connections, repeatable.
  An earlier version of this paragraph claimed the pre-token transport was bounded
  "so an unauthenticated loopback peer cannot ... kill the daemon"; the timeout
  *was* the denial-of-service primitive, not the mitigation. Now the accept thread
  only accepts, a per-connection reader performs the unauthenticated work (read,
  parse, constant-time token check) so a silent peer burns only its own 2s budget,
  and a single worker thread is the only thread that touches the session — required
  because `PtySession` is not thread-safe. Measured after: an authenticated request
  is served in 0.00s with nine silent peers holding connections. Request size is
  bounded (4 MiB) so memory exhaustion is covered separately. Locked by
  `tests/test_daemon_concurrency.py`, which drives the real accept loop and is
  mutation-verified against a reverted serial design.
  Since 0.2.0 the hardening also covers: session ids are
  validated before any registry path use (no traversal); on POSIX the per-session
  registry directory is created `0700` and refused if it is a symlink or owned by
  another user — that block is **POSIX-only**, and on Windows none of the three
  checks runs, because the code returns at the `os.name == "nt"` branch *before*
  the symlink test, the ownership test and the `chmod`; on Windows the same branch
  instead secures the directory the Windows way (explicit DACL, verified by
  read-back, refusal if unproven — above), and the POSIX branch is byte-for-byte
  unchanged; registry files are
  created `O_EXCL` on both platforms (+`O_CLOEXEC`/`O_NOFOLLOW` on POSIX) so a
  capability cannot be replaced; the driven child does **not** inherit
  `SMARTCLI_TUI_TOKEN`; `--env` may not override SmartCLI control variables
  (compared **uppercased**, because Windows environment names are
  case-insensitive and CPython upcases keys on assignment — an exact-case check
  let `--env smartcli_tui_token=…` re-inject the very capability the daemon pops;
  the deny-list also covers `SMARTCLI_ROOT`, `SMARTCLI_MAX_SESSIONS` and
  `SMARTCLI_AUTO_INSTALL`); a request that is not a JSON object is rejected before
  dispatch, so an unauthenticated peer cannot be answered with an interpreter
  exception; `close` refuses to delete a session's registry entry while the
  recorded daemon cannot be shown to be gone, because the file is the only store
  of both the token and the pid and a socket timeout is not proof of death
  (`--force` overrides) — and the "shown to be gone" half is decided by
  **process identity, not by pid alone**: the daemon records its own creation
  time at spawn (`GetProcessTimes` on Windows, `/proc/<pid>/stat` field 22 on
  Linux, not cheaply available on macOS), and the creation time, not the pid, is
  the name that survives. It gates the unlink in both directions: a pid that
  answers but was created at a different time has been recycled, and a pid that
  is gone while some process still carries the recorded creation time means the
  entry no longer holds the pid of a live daemon — either way the recorded
  daemon is treated as alive and the entry is kept for `--force` to decide. A
  pid-only check cannot make that second decision at all, and did not: writing a
  live entry and overwriting only its `pid` field with a dead pid used to delete
  the file, the token and the pid of a process that was still running (rc=0,
  empty stderr). That case, and the one beside it — a dead pid whose recorded
  creation time nothing alive carries, which is still cleaned up silently — are
  gated against a real process table in `tests/test_drive_security.py`. An OS
  that refuses to report a creation time is also treated as
  alive, and so is a host that could not be enumerated for a process carrying
  the recorded time.
  That name is only as sharp as the platform's clock allows. On Windows it is a
  FILETIME (100 ns since 1601), but on Linux `starttime` counts **clock ticks
  since boot** (typically 100/s), so two processes born inside the same tick
  carry the *same* value: the identity is tick-granular, not unique, and the
  process-table walk can reach either of them first — so the refusal may name a
  colliding sibling rather than the recorded daemon. That is the safe direction,
  and it is worth stating rather than leaving implied: a collision can only ever
  cost a false **refusal** (an entry whose daemon has in fact exited stays on
  disk until `--force`, and the kill hint may name the wrong pid), never a false
  "gone", because the recorded daemon's own value is present for exactly as long
  as the daemon lives.
  On macOS there is no cheap creation time for another process at all, so
  `pid_born` is `null` on every entry this program writes and every close there
  takes the weaker pid-only branch below — which still cleans up a dead daemon,
  so macOS users accumulate nothing. An entry on macOS that *does* carry a
  recorded creation time therefore cannot have been written there: it arrived
  from another platform (`SMARTCLI_TUI_DIR` aimed at a shared or restored
  registry) or was written by hand, it can never be checked on that host, and
  `close` will keep it and refuse until `--force`. That is the intended answer
  rather than a leak in the cleanup path — the only evidence such a host has is
  the entry's own pid, which is exactly the field an altered entry gets wrong —
  but it is a real, permanent need for `--force` in that case, so it is stated
  here instead of being left to be discovered.
  The two tick-collision and macOS cases are what the platform-split legs of
  `test_close_is_identity_aware` assert in each form.
  **What the creation time is NOT: proof of who wrote the
  entry.** Anything able to write the registry file can write a self-consistent
  `pid`+`pid_born` pair, or omit `pid_born`, or delete the file outright — which
  is the stronger version of the same attack, and no check inside the file can
  answer it. This is a consistency check on an entry, not an authorisation one.
  The one case identity cannot settle is a legacy entry written before that
  field existed: it falls back to the weaker pid-only test and says so, in the
  close output and in a warning, rather than inventing an identity; and the
  session count (default 8, `SMARTCLI_MAX_SESSIONS`) and
  terminal dimensions are bounded. Reports about token bypass, screen-content
  leaks to an unauthenticated peer, or session hijack are in scope.
- **The MCP server wrapper** (`skills/drive-tui/scripts/mcp_server.py`), which
  exposes the same daemon verbs. It must never expose an unauthenticated verb —
  it reuses the token-auth client path.
- **The wait family's child-death option** (`start --detect-child-exit`,
  `run --detect-child-exit`, `detect_child_exit` on the MCP `start` tool). It is
  **configuration, not a capability**, and the distinction is the whole of its
  security story: it adds no daemon action, no new verb, no new socket, and no
  new data — it makes the waits this daemon already serves consult
  `PtySession.is_alive()` once per poll, and report the outcome in a field the
  caller was already entitled to. The per-session token gate is unchanged and is
  checked before the request reaches any of it, so turning it on cannot make an
  unauthenticated peer learn anything it could not already ask for; a request
  with a bad or missing token is still refused with no reply fields at all
  (asserted in `tests/test_drive_security.py`). The flag itself travels on the
  daemon's argv, like `--cwd` and `--cols` — it is not a secret, and the value
  that *is* a secret (the token) still travels in an environment variable, never
  in argv.
- **What is deliberately NOT reachable from a session.** The screen-revision
  wait baseline, the terminal-mode registry and the session event log are
  library-only: importable from `smartcli_core`, and absent from the daemon and
  the MCP surface. That is a decision, not an oversight, and it is worth stating
  in a security document because it bounds the surface: no session request, in
  either direction, can reach them, so there is no input to fuzz and nothing for
  an unauthenticated peer to aim at. The event log in particular would have been
  a disk-write surface carrying whatever the driven program printed and whatever
  you typed at it; keeping it out of the shipped verbs is why that surface does
  not exist.
- **`smartcli_core`** PTY handling and the `pyte`-backed perception chain.

## Out of scope

- The visual effects (`cmd-art`) and layout engine (`tui-ui`) are pure
  frame producers with no network or auth surface.
- Anything requiring an attacker to already have local access equivalent to the
  session owner — **conditional on the token file actually being private to that
  owner**. That premise is now *established* rather than assumed on both
  platforms: on POSIX from `0600` inside `0700`, on Windows from the explicit,
  read-back-verified DACL described above, so a host that widens the temp
  directory's ACL no longer changes the answer. The clause has not been widened
  with it, and the limit is worth stating plainly: `NT AUTHORITY\SYSTEM` and
  `BUILTIN\Administrators` are named trustees by design, so an account with
  administrative privilege — or anything that can run as SYSTEM, which on a
  dev box means some local agent sandboxes — can read the token and drive the
  child, and that is administrative access equivalent to the owner, not less.
  A DACL that is re-applied by sandbox software or group policy *after* our
  read-back is caught the next time the registry is used, because the check runs
  on every write — of the directory **and of the file that holds the token**,
  each verified on the same fail-closed terms — not once at install; until then
  the exposure is exactly the one the verification just ruled out. The registry
  directory is not the only copy: the daemon holds the token in memory for the
  life of the session, so read access to that process reaches it too. Note the
  rest of this clause: it does **not** cover an unprivileged local account that
  cannot read the token file, and the loopback port is discoverable with
  `netstat` and no privilege — which is why the head-of-line denial of service
  above was treated as in scope and fixed rather than dismissed under this
  clause.
- `research/cc-decompiled/` and `research/real-frames/` are gitignored and not
  part of any release.

## Supported versions

Fixes land on `main` and ship in the next PyPI release
(`pip install --upgrade smartcli-toolkit`). Only the latest released version is
supported.
