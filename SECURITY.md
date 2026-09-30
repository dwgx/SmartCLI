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
  would still be a claim, so `_ensure_reg_dir` **reads the effective DACL back**
  and walks its ACEs; if it cannot be established, no capability token is
  written and the command exits with a refusal naming the path and the `icacls`
  to run. A false "still permissive" costs the user one command; a false
  "private" hands a stranger control of a live child process, so the
  unproven case is the refused one. The same DACL is set explicitly on each
  registry file, so what lands inside the directory is a fact about this call
  rather than a consequence of a token default nobody chose.
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
  exception; `close` refuses to delete a session's registry entry while that
  daemon's pid is still alive, because the file is the only store of both the
  token and the pid and a socket timeout is not proof of death (`--force`
  overrides) — and the "still alive" half is checked by **process identity, not
  by pid alone**: the daemon records its own creation time at spawn
  (`GetProcessTimes` on Windows, `/proc/<pid>/stat` field 22 on Linux, not
  cheaply available on macOS), and a pid that answers but was created at a
  different time has been recycled, so the recorded daemon is treated as alive
  and the entry is kept for `--force` to decide. An OS that refuses to report
  the creation time is also treated as alive. The one case identity cannot
  settle is a legacy entry written before that field existed: it falls back to
  the weaker pid-only test and says so, in the close output and in a warning,
  rather than inventing an identity; and the session count (default 8,
  `SMARTCLI_MAX_SESSIONS`) and
  terminal dimensions are bounded. Reports about token bypass, screen-content
  leaks to an unauthenticated peer, or session hijack are in scope.
- **The MCP server wrapper** (`skills/drive-tui/scripts/mcp_server.py`), which
  exposes the same daemon verbs. It must never expose an unauthenticated verb —
  it reuses the token-auth client path.
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
  on every write, not once at install; until then the exposure is exactly the
  one the verification just ruled out. The registry directory is not the only
  copy: the daemon holds the token in memory for the life of the session, so
  read access to that process reaches it too. Note the rest of this clause: it
  does **not** cover an unprivileged local account that cannot read the token
  file, and the loopback port is discoverable with `netstat` and no privilege —
  which is why the head-of-line denial of service above was treated as in scope
  and fixed rather than dismissed under this clause.
- `research/cc-decompiled/` and `research/real-frames/` are gitignored and not
  part of any release.

## Supported versions

Fixes land on `main` and ship in the next PyPI release
(`pip install --upgrade smartcli-toolkit`). Only the latest released version is
supported.
