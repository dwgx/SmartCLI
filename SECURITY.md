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
  `ps`/Task Manager) and persisted in a `0600` per-session registry file. The
  pre-token transport is bounded (max request size, per-connection timeout) so an
  unauthenticated loopback peer cannot exhaust memory or kill the daemon with
  malformed bytes. Reports about token bypass, screen-content leaks to an
  unauthenticated peer, or session hijack are in scope.
- **The MCP server wrapper** (`skills/drive-tui/scripts/mcp_server.py`), which
  exposes the same daemon verbs. It must never expose an unauthenticated verb —
  it reuses the token-auth client path.
- **`smartcli_core`** PTY handling and the `pyte`-backed perception chain.

## Out of scope

- The visual effects (`cmd-art`) and layout engine (`tui-ui`) are pure
  frame producers with no network or auth surface.
- Anything requiring an attacker to already have local access equivalent to the
  session owner (they can read the `0600` token file by definition).
- `research/cc-decompiled/` and `research/real-frames/` are gitignored and not
  part of any release.

## Supported versions

Fixes land on `main` and ship in the next PyPI release
(`pip install --upgrade smartcli-toolkit`). Only the latest released version is
supported.
