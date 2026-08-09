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
  `ps`/Task Manager) and persisted in a `0600` per-session registry file.
  **Known residual (do not read the bound below as a fix):** the accept loop is
  serial, so an unauthenticated loopback peer that connects and sends no newline
  head-of-line blocks every other caller for the duration of its read budget.
  That budget is split — 2s before the token check, 60s only for an authenticated
  caller's reply, and the pre-auth side is re-armed against a fixed deadline so a
  peer dribbling bytes cannot renew it indefinitely. Measured, nine held
  connections fell from 540s to 18s: a 30× reduction, **not** a fix, because an
  attacker who keeps reconnecting still degrades service. The real answer is
  per-connection threading, which is blocked on `PtySession` not being
  thread-safe (tracked as A0-DAEMON-CONCURRENCY in `NEXT-STEPS.md`). An earlier
  version of this paragraph claimed the transport was bounded "so an
  unauthenticated loopback peer cannot ... kill the daemon" — the timeout *was*
  the denial-of-service primitive, not the mitigation. Request size is bounded, so
  memory exhaustion is genuinely covered. Since 0.2.0 the hardening also covers: session ids are
  validated before any registry path use (no traversal); the per-session registry
  directory is created `0700` and refused if it is a symlink or owned by another
  user; registry files are created `O_EXCL` (+`O_NOFOLLOW` on POSIX) so a
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
  overrides); and the session count (default 8, `SMARTCLI_MAX_SESSIONS`) and
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
  session owner (they can read the `0600` token file by definition). Note the
  limit of this clause: it does **not** cover an unprivileged local account that
  cannot read the token file, and the loopback port is discoverable with `netstat`
  and no privilege — which is why the head-of-line residual above is listed as a
  known issue rather than dismissed as out of scope.
- `research/cc-decompiled/` and `research/real-frames/` are gitignored and not
  part of any release.

## Supported versions

Fixes land on `main` and ship in the next PyPI release
(`pip install --upgrade smartcli-toolkit`). Only the latest released version is
supported.
