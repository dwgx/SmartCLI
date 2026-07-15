---
name: drive-tui
description: >-
  Drive interactive terminal (TUI) programs — CLIs, REPLs, installers, menu
  apps, agent CLIs, and editors like vim — through a PTY, reading semantic
  screen snapshots. A pattern library classifies a screen (REPL, menu, pager,
  fzf search, confirm dialog, form, spinner, wizard) and drives it with a ready
  recipe. Use when a program expects a live terminal (arrow-key menus, prompts,
  spinners, password fields, curses UIs), or when a piped command hangs or
  prints nothing.
allowed-tools: Bash, Read
version: 0.1.6
---

# drive-tui

Drive interactive terminal programs the way a human does: look at the screen, decide, press keys, wait, look again. A normal `subprocess`/pipe can't do this — line-buffered pipes hide menus, spinners, and prompts, and many programs refuse to run without a real TTY. This skill uses `smartcli_core` (a PTY + `pyte` screen model + semantic snapshots + readiness waits) behind a thin CLI, `scripts/tui.py`.

## When to use
- Launching a program that draws a full-screen or line-mode UI and expects keystrokes (REPLs, installers, `vim`, agent CLIs, arrow-key menus, y/n prompts, password entry).
- A piped command hangs, prints nothing, or says "not a terminal".
- You need to see what an interactive program is showing right now, then act on it.
- Do NOT use for non-interactive commands whose full output you just want captured — run those directly.

## Core mental model: the perceive → decide → act loop

Never fire keystrokes blind and never guess with `sleep`. Every interaction is one turn of this loop:

1. **Perceive** — take a snapshot. Read the header line (cursor position, selected row, status bar, errors) and the row-numbered body.
2. **Decide** — classify the screen: is it a menu, a text prompt, a confirmation, a spinner still loading, an error, or a finished result? Decide the single next action.
3. **Act** — translate intent into key tokens and send them (`send-line`, `send-text`, or `keys`).
4. **Wait** — call `wait` / `wait-regex`. NEVER `sleep`. The wait pumps output until the screen settles or an expected marker appears.
5. **Confirm** — re-snapshot and verify the screen changed as expected before the next action.

## Setup

`scripts/tui.py` adds the repo root to `sys.path` itself, so run it from anywhere. It locates `smartcli_core` via `smartcli_bootstrap.locate_core()`: `$SMARTCLI_ROOT` → walk up every parent of the script for a dir containing `smartcli_core/__init__.py` → a bundled `_vendor/` next to the skill → an existing pip install (there is no fixed "N levels up"). It also needs the deps `pyte` + `pywinpty` (Windows) importable. Set `SMARTCLI_ROOT` to override, or run `tui.py doctor` to report where the core resolved and which deps are missing.

All commands below are shown from the repo root. Use the exact form:
`python skills/drive-tui/scripts/tui.py <subcommand> ...`

## Two ways to drive

### A. Persistent session (interactive, multi-turn) — the default
A detached daemon owns one live program; each command connects over a localhost-only socket, so state survives across separate shell calls. This is the real perceive→decide→act loop.

1. Start (prints a session id — capture it):
   `python skills/drive-tui/scripts/tui.py start --cmd "python" --cols 100 --rows 30`
2. Wait for the first prompt, then snapshot is printed automatically:
   `python skills/drive-tui/scripts/tui.py wait-regex --id <SID> ">>> " --timeout-ms 15000`
3. Act, then wait, then it re-snapshots:
   `python skills/drive-tui/scripts/tui.py send-line --id <SID> "print(6*7)"`
   `python skills/drive-tui/scripts/tui.py wait --id <SID>`
4. Snapshot any time without acting:
   `python skills/drive-tui/scripts/tui.py snapshot --id <SID>`
   Add `--json` for the structured `Snapshot.to_json()` form (selected span, menu_items, errors).
5. Check liveness / list / close:
   `python skills/drive-tui/scripts/tui.py alive --id <SID>`   (exit 0 alive, 1 dead)
   `python skills/drive-tui/scripts/tui.py list`
   `python skills/drive-tui/scripts/tui.py close --id <SID>`   (always close when done)

Subcommands: `start`, `snapshot`, `send-text`, `send-line`, `keys`, `wait`, `wait-regex`, `alive`, `close`, `list`. `wait`/`wait-regex` print liveness + reason to stderr and the snapshot to stdout.

### B. One-shot script (batch, non-interactive)
When you already know the whole sequence, run it in a single process against a fresh program. No session to manage. Write a JSON list of steps to a file and run:
`python skills/drive-tui/scripts/tui.py run --cmd "python" --steps steps.json --cols 100 --rows 30`

Step objects (executed in order; each `wait_*`/`snapshot` prints a snapshot):
- `{"action":"send_text","text":"..."}` — type literally, no Enter.
- `{"action":"send_line","text":"..."}` — type + Enter.
- `{"action":"send_keys","keys":["Down","Down","Enter"]}` — key tokens.
- `{"action":"wait_ready","marker":"regex"}` — wait for marker OR stability (marker optional).
- `{"action":"wait_regex","pattern":"regex","timeout_ms":10000}` — wait strictly for the regex.
- `{"action":"snapshot"}` — print the current screen.

### C. MCP server (drive from any MCP client)
`scripts/mcp_server.py` exposes the same verb surface as MCP tools, so any MCP
client (Claude Desktop, an agent framework) can drive TUIs without shelling out.
It reuses the CLI's client layer, so the **per-session capability token is
attached automatically** and no verb is exposed unauthenticated. Install the
extra and run it (stdio transport):
`pip install "smartcli-toolkit[mcp]"`
`python skills/drive-tui/scripts/mcp_server.py`
Tools: `start`, `list_sessions`, `snapshot`, `send_text`, `send_line`,
`send_keys`, `wait_regex`, `wait_ready`, `alive`, `resize`, `close` — a 1:1 map
of the daemon verbs. The same perceive → decide → act loop applies.

## Silent / background operation — driving without disturbing the user

**By design, driving a CLI here is already headless and non-intrusive — there is no window to hide, and the user's focus is never stolen.** This is a property of the PTY model, not an extra feature:

- The program runs inside a **pseudo-terminal**: an in-memory character grid (ConPTY via `pywinpty` on Windows, the stdlib `pty` on POSIX). The CLI believes it has a real terminal — so it still draws menus, the cursor, colours — but that "terminal" **exists only in memory**. There is **no GUI window, no console window, nothing painted on screen** for the user to see or lose focus to.
- The persistent-session daemon is launched **fully detached**: on Windows with `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` — no console window is created, so it never steals focus (this deliberately replaced the older `DETACHED_PROCESS`, which does *not* prevent a conhost window from flashing up and grabbing focus); on POSIX with `start_new_session=True` (no controlling terminal). Its stdin/stdout/stderr are all `DEVNULL`, so it never prints into the user's shell.
- So the loop is invisible: the AI `start`s a program, `snapshot`s the in-memory screen, `send-keys`, `wait`, `snapshot` again — all while the user keeps typing in their editor, undisturbed. Nothing pops up, nothing grabs the cursor.

**Two intents, both already supported — this is a choice you make, not code you write:**

1. **Silent (default).** Just drive it. The AI reads snapshots itself and reports a summary to the user in chat. The user never sees the raw TUI. This is the normal mode and needs nothing special — it is what every example above does.
2. **Show the user what you saw.** Because a snapshot is plain text/ANSI, you can surface it on demand: paste `snapshot` output into the reply, or render it to a PNG with `tools/screenshot` (`shot.render_bytes_to_screen` → `screen_to_png`) and show that. The program still runs headless; you are only *echoing* what the AI perceived, when the user asks.

**How to decide (default hidden; you judge the scenario).** The default is **silent** — drive, perceive, summarise; the user does not see the raw TUI. Whether to surface a snapshot is a judgment call *you* make each time, in this priority order:

1. **User asked to see it** → show it. ("show me the menu", "what does it look like", "paste the screen".) Explicit request always wins.
2. **The user must choose / the screen is the point** → show it. A menu they need to pick from, a diff/preview they should eyeball, an error you can't resolve alone, or when the TUI's *appearance* is what they care about.
3. **It's a means to an end** → stay silent, report the outcome. If the user wanted a *result* ("switch the model to Opus", "answer the installer's prompts"), just do it and say what happened — the intermediate screens are noise to them.
4. **Unsure and it's cheap to show** → lean toward a short snapshot; seeing is reassuring. **Unsure and it's long/noisy** → summarise, and offer ("want to see the raw screen?").

Never open a visible terminal window to "let the user watch" — that is the intrusion the PTY model avoids (and would steal their focus). Echo a snapshot (text or a `tools/screenshot` PNG) instead.

**One real caveat (be honest about it):** a few programs behave differently with no real TTY — e.g. ConPTY may delay the first prompt ~3s (use `wait-regex` with a 15s timeout, never a bare `wait` on startup), and a bare Ctrl-C can be unreliable under ConPTY (close + re-open instead). These are noted in *Constraints / gotchas* below.

## Reading a snapshot

`to_text()` output = one header line + row-numbered body:
```
[screen 24x80] cursor=r3c4  selected=r3[0:80]">>>"(cursor_line)  status="..."  errors=1
  0 | Python 3.14.6 ...
  3 | >>>
```
- Header: `cursor=rNcM`, optional `selected=...`, `status="..."`, `title`, `errors=N`, `screen_reverse`.
- Body: `<row><*>| text`. A `*` marks a selected/highlighted row. Blank runs collapse to `...`.
- **`selected_line` is the key menu signal.** In an arrow-key menu the highlighted (reverse-video / colored) row is the current choice — the snapshot surfaces it as the `*` row and in the header `selected`. Use it to know where the cursor sits before pressing Up/Down.

## Deciding: classify the screen
- Prompt (`>>> `, `$ `, `Password:`, `Continue? [y/N]`) → send the answer with `send-line`, or a single key with `keys`.
- Menu (a `*`/`selected` row, list of options) → move with `keys Up`/`keys Down`, choose with `keys Enter`. Do not type the option text.
- Spinner / progress / still loading → do not act; call `wait` again (it caps at `max_wait_ms` and returns the last screen).
- Error (`errors=N` in header, red text, "Traceback"/"failed") → stop and read; do not keep sending input.
- Finished result → capture the snapshot; act or close.

## Translating intent to keys (`keys` subcommand / `send_keys`)
Named tokens: `Enter Tab BackTab Space Backspace Delete Escape Up Down Left Right Home End PageUp PageDown Insert F1`–`F12`.
Combos: `C-c` / `^C` (Ctrl+C), `M-x` (Alt+x). Anything else is sent literally.
- Menus/keys → `keys`. Free text + submit → `send-line`. Text without submit (fills a field) → `send-text`.
- `send-line` submits with `\r`. A raw-mode app that needs `\n` → use `send-text "...\n"`.
- **Slash-commands (`/model`, `/help`, …) on Git Bash / MSYS — use `--stdin`.** A leading `/` in a native-command argument is rewritten to a Windows path by MSYS path-conversion *before Python sees it* (`/model` arrives as `D:/Software/Git/model` — the tool then faithfully types the garbage). This is a shell quirk, not a tool bug. The robust, shell-agnostic fix is to pipe the text so it never rides in argv: `printf '/model' | python … send-line --id <SID> --stdin`. (`echo -n` works too.) Alternatives that also work but are easier to forget: prefix `MSYS_NO_PATHCONV=1`, or double the slash (`//model`). Prefer `--stdin` — it's immune on Git Bash, cmd, PowerShell, and POSIX alike. **Do not** try to type a slash-command with the `keys` subcommand: there is no `slash` token — unknown tokens are typed literally, so `keys slash` types the word "slash".

## Choosing the right wait — do NOT sleep
- Know the exact text that means "ready" (a prompt, a banner) → `wait-regex <pattern>`. **Prefer this.** It watches strictly for the regex and will NOT return early.
- Don't know the marker (screen just needs to settle after a keystroke) → `wait` (marker optional): returns on stability or a marker, capped by timeout.
- **Startup gotcha:** a program can sit quiet for seconds before its banner appears (Python's REPL banner arrives ~3s after spawn on Windows ConPTY). Plain `wait`/`wait_ready` may declare `STABLE` on the still-blank screen during that gap. So for the FIRST prompt after `start`, use `wait-regex` with a generous `--timeout-ms` (e.g. 15000), not bare `wait`.
- Regex tips: match against the whole screen text. Anchoring with `$` needs multiline semantics — prefer a loose marker like `">>> "` over `">>> $"`. Confirm the result with a follow-up `snapshot`.

## Recovering when a program doesn't respond
1. Re-`snapshot` — confirm it actually didn't change (you may have missed output).
2. `alive --id <SID>` — if dead, the child exited; read the final snapshot for the reason, then `close`.
3. Still alive but stuck: try `keys Enter` (dismiss a pager/prompt) or `keys Escape` (leave a mode).
4. Interrupt a running command: `keys C-c`. **Windows caveat:** under ConPTY a raw Ctrl-C byte does NOT reliably raise an interrupt in a line-mode child (verified — `time.sleep` in the Python REPL was not interrupted). On Windows, if `C-c` fails, the reliable recovery is `close --id <SID>` and `start` a fresh session. On POSIX, `C-c` works normally.
5. Always `close` sessions you started (frees the daemon and the child).

## Constraints / gotchas
- Never blind-`sleep` to wait for output — use `wait` / `wait-regex`; they pump the PTY and have hard timeouts.
- Always re-snapshot after acting; the snapshot before your keystroke is stale.
- Arrow/nav keys are **adaptive**: `send_keys` reads the live screen's cursor-key mode and emits SS3 (`ESC O A`) when the program has enabled DECCKM (application cursor keys — most full-screen/curses TUIs), else CSI (`ESC [ A`). This is auto — you just send `keys Up`. (Verified on real Linux ncurses; before this, CSI-only arrows silently did nothing in DECCKM apps.) If a rare app still ignores arrows, re-snapshot and fall back to its letter/number shortcuts.
- The daemon binds `127.0.0.1` only — local process control, no network exposure.
- Paths above are relative to this skill's folder; run the script by its path from the repo root.
- Deeper API details: read `references/core_api.md` only when you need field-level specifics.

## Known limitations & self-improvement (read when something doesn't work)

This skill is honest about its gaps, and it is **built to be extended by the AI using it**. If you hit a wall, don't just work around it silently — research it, fix it if you can verify the fix, and record what you learned so the next run benefits.

**Where the gaps are tracked:** `references/LIMITATIONS.md` — a short, living log of known-unfixed edges, environment caveats, and fixes that have already landed (with how each was verified). **Read it first when a program misbehaves** — your problem may already be solved or explained there.

**The self-improvement loop (when you hit a genuine limitation):**
1. **Reproduce narrowly.** Drive the failing case with the smallest command + snapshot that shows the wrong behavior. Capture the exact bytes/screen, not a guess.
2. **Research the mechanism.** Check `references/LIMITATIONS.md` and the knowledge graph (`knowledge/INDEX.md`) first. If it's a terminal-protocol issue, the cause is usually a mode (DECCKM, bracketed paste, alt-screen) or a timing gap — verify with a tiny probe, don't assume.
3. **Verify on the real path — never head-canon.** A fix is only real if you drove the actual program and saw it work (a green preview or a mocked backend proves nothing). If the fix touches `smartcli_core`, it is DO-NOT-MODIFY-except-under-verification: prove it on the real run path, and re-run the drive-probe suite (`tests/_drive_probe*.py`, `tests/_tui_cli_probe.py`) to show zero regression. On a non-Windows host, also run `tests/_sandbox_posix_backend.py`.
4. **Record it.** Append a dated entry to `references/LIMITATIONS.md`: the symptom, the root cause, the fix (or "still open, with reason"), and exactly how you verified it. One honest paragraph beats a vague TODO.
5. **Then continue using the skill** with the fix in place.

The point: the skill should get *more* capable each time it's pushed against a new program, and every future run inherits that — the AI's findings are written back into the tool, not lost in one conversation.

## Knowledge base — look before you build
Before scripting a new interaction or pattern, consult the SmartCLI knowledge graph at
`D:/Project/SmartCLI/knowledge/INDEX.md`. Its `tui-patterns/` domain is a 1:1 conceptual
map of the 8 recipes below — [[list-menu-navigation]], [[fuzzy-search-filter]],
[[pager-navigation]], [[confirm-yes-no-dialog]], [[progress-spinner-waiting]],
[[form-field-input]], [[repl-session]], [[wizard-installer-flow]] — plus the sourced
foundations behind every gotcha in this skill: [[application-cursor-mode]] (the exact
arrow-keys-don't-move bug), [[quiescence-detection]] and [[snapshot-stability-hash]]
(how `wait` decides "settled"), [[key-encoding-reference]] (key tokens → bytes),
[[cursor-row-binding]] and [[verify-movement-step-by-step]] (why matches bind to the
cursor row and every action re-snapshots). Read the relevant note before inventing a
recipe from scratch.

## Pattern library — classify a screen, drive it with a recipe

Above is the manual loop through `scripts/tui.py`. For recurring paradigms there is a Python pattern library (`skills/drive-tui/patterns/`) that recognizes a screen and drives it for you. It works on `smartcli_core` `Snapshot`/`PtySession` objects, so use it from Python (import `patterns`), not the `tui.py` CLI. Add `skills/drive-tui` to `sys.path`, or run from there.

### Classify / explain a screen
- `classify(snapshot, threshold=0.05) -> [(Pattern, confidence), ...]` — every registered pattern scored 0..1 against the snapshot, highest first. A pattern whose `matches()` raises is scored 0, never poisoning the ranking.
- `explain(snapshot) -> str` — a human/agent-readable description: raw facts (size, cursor, highlighted row + reason, menu spans, status bar, errors, screen-reverse) followed by the ranked paradigms with confidences.

```python
import sys; sys.path.insert(0, "skills/drive-tui")
from patterns import registry
from patterns.classify import classify, explain

snap = session.snapshot()          # a smartcli_core PtySession
print(explain(snap))               # what does this screen look like?
best, conf = classify(snap)[0]     # top paradigm
```

### The 8 recipes (registry names → tags)
Live catalog: `[p.name for p in registry.all_patterns()]`.

| name | drives | intent | tags |
|------|--------|--------|------|
| `repl` | interactive REPL/shell prompt | one code line to run | repl, shell, prompt, interactive |
| `menu_select` | arrow-key vertical menu | int index or substring | menu, list, navigation |
| `pager` | less/more/man/git-log | `to_end` / `next_page` / `search:<term>` | pager, scroll |
| `search_filter` | fzf / Ctrl-R / palette | the query string | fuzzy, filter, incremental |
| `confirm` | `[y/N]` / `(yes/no)` dialog | bool (or yes/no string) | dialog, yesno |
| `form` | labelled input fields | dict/list/str of field values | form, input |
| `progress` | spinner / progress bar | optional completion regex | spinner, progress, wait |
| `wizard` | multi-step installer | list of per-step actions | wizard, multistep, installer |

### Call a recipe
Get the registered singleton and call `.drive(session, intent, **kw)`. It runs the perceive→act→wait→confirm loop against the live session and returns a `PatternResult(ok, detail, snapshot, data)` — `ok` is a real screen assertion, `snapshot` is the last screen as evidence, `data` is the pattern-specific payload.

```python
from patterns import registry

# REPL: run a line, confirm a fresh prompt returned + cursor advanced
res = registry.get("repl").drive(session, intent="6*7")
assert res.ok; print(res.data["output"])          # ['42']

# menu: move the highlight to a target and press Enter (confirms the bar moved)
registry.get("menu_select").drive(session, intent="Charlie")   # or intent=2
registry.get("menu_select").drive(session, intent=0, press=False)  # position only

# pager: page to the bottom
registry.get("pager").drive(session, intent="to_end", max_pages=200)

# search: narrow a fuzzy list, then pick the top match
registry.get("search_filter").drive(session, intent="grapef", stop_at=1, accept=True)

# confirm: answer yes (commits with Enter if a line-mode child only echoed)
registry.get("confirm").drive(session, intent=True)

# form: fill fields, Tab between, Enter to submit
registry.get("form").drive(session, intent={"Name": "Ada", "Email": "a@b.c"})

# progress: wait for a done marker, else for the animation to settle (hard ceiling)
registry.get("progress").drive(session, intent=r"DONE!", max_wait_ms=60000)

# wizard: drive a scripted multi-step flow
registry.get("wizard").drive(session, intent=[
    {"keys": ["Down", "Enter"]}, {"pattern": "confirm", "value": True}, None])
```
Module-level convenience helpers: `patterns.recipes.repl_session.run_line(session, code, **kw)` and `patterns.recipes.paginate.read_all(session, max_pages=200, key="Space") -> (text, PatternResult)` (accumulates the pager's full text across pages, dedup'ing repainted boundary rows).

Recipe `drive` kwargs worth knowing:
- `repl`: `expect=<regex>` (confirm a marker instead of waiting for STABLE), `timeout_ms`, `quiet_ms`, `min_wait_ms`.
- `menu_select`: `max_steps`, `settle_ms`, `press` (send Enter, default True), `enter_wait_ms`.
- `pager`: `max_pages`, `key` (`Space`|`PageDown`|`f`, default `Space`; `f` is the less/more forward-page key).
- `search_filter`: `incremental` (default True), `stop_at` (match-count threshold, default 1), `accept` (Enter to pick), `settle_ms`.
- `form`: `next_key` (default `Tab`), `submit` (default `Enter`); intent may be a dict, a list of `(label, value)`, or a single string.
- `progress`: `max_wait_ms`, `quiet_ms` (pure observer, sends no keys; returns `timeout` rather than a false complete if it never settles).
- `wizard`: `advance_key` (default `Enter`), `max_steps`. Each intent item is `{"pattern": name, "value": intent}`, `{"keys": [...]}`, or `None`/`{}` for auto (classify + best recipe, fallback `advance_key`).

Recipes fail loud on bad params (empty/mistyped intent raises `ValueError`) rather than doing something silently wrong.

### Add a NEW pattern
Drop one module in `patterns/recipes/` — pkgutil auto-imports it and `@register` wires it into `all_patterns`/`classify`. A module that fails to import is logged (stderr + `registry.load_errors()`) and skipped; it never breaks the rest of the catalog. Avoid import-time side effects that can't fail-soft.

Contract (`patterns/base.py`):
- Subclass `Pattern`; set `name` (lowercase, unique), `description`, `tags`.
- `matches(self, snapshot) -> float` (0..1): cheap, **no side effects**. Bind signals to the CURSOR ROW and cell attributes (`selected`, `menu_items`, `status_bar`) — NOT bare body text, since prompts and `[y/N]` strings also echo in scrollback. Use the helpers `Pattern.cursor_row_text(snap)`, `Pattern.last_rows_text(snap, n)`, `Pattern.visible_text(snap)`, `Pattern.rx(pat, text, flags)`.
- `drive(self, session, intent=None, **kw) -> PatternResult`: perceive→act→wait→confirm. NEVER blind-`sleep`; always re-snapshot after acting; always bound waits (`wait_stable`/`wait_for` with a hard ceiling). Return `PatternResult(ok, detail, snapshot=<last snapshot>, data={...})` where `ok` is asserted from the screen.
- Decorate with `@patterns.registry.register` above the class.

```python
from smartcli_core import PtySession, Snapshot
from patterns.base import Pattern, PatternResult
from patterns import registry

@registry.register
class TabBar(Pattern):
    name = "tabbar"
    description = "a top tab bar; switch tabs with the arrow/Tab keys."
    tags = ("tabs", "navigation")

    def matches(self, snapshot: Snapshot) -> float:
        row0 = next((e[1] for e in snapshot.lines if e != "..." and e[0] == 0), "")
        return 0.8 if self.rx(r"\[.+\]\s+\[.+\]", row0) else 0.0

    def drive(self, session: PtySession, intent=None, **kw) -> PatternResult:
        before = session.snapshot()
        session.send_keys(["Right"])
        session.wait_stable(quiet_ms=120, max_wait_ms=1500)
        after = session.snapshot()
        moved = after.cursor != before.cursor
        return PatternResult(ok=moved, detail="switched tab" if moved else "no move",
                             snapshot=after, data={"moved": moved})
```

Fault isolation is verified: a recipe module that crashes at import leaves all other recipes registered, and `classify()` is safe on a degenerate snapshot.

## Worked example — driving the Python REPL (persistent session)

```
# 1. start -> capture the id it prints
$ python skills/drive-tui/scripts/tui.py start --cmd "python" --cols 80 --rows 24
s21576_90197

# 2. PERCEIVE the first prompt (wait-regex, generous timeout for the ~3s banner gap)
$ python skills/drive-tui/scripts/tui.py wait-regex --id s21576_90197 ">>> " --timeout-ms 15000
# matched=True alive=True
[screen 24x80] cursor=r3c4  selected=r3[0:80]">>>"(cursor_line)
  0 | Python 3.14.6 ... on win32
  2 | Type "help", "copyright", "credits" or "license" for more information.
  3 | >>>

# 3. DECIDE: it's a prompt. ACT: send an expression. WAIT + CONFIRM.
$ python skills/drive-tui/scripts/tui.py send-line --id s21576_90197 "print(6*7)"
$ python skills/drive-tui/scripts/tui.py wait --id s21576_90197
[screen 24x80] cursor=r5c4 ...
  3 | >>> print(6*7)
  4 | 42
  5 | >>>

# 4. done -> exit cleanly, then close the session
$ python skills/drive-tui/scripts/tui.py send-line --id s21576_90197 "exit()"
$ python skills/drive-tui/scripts/tui.py close --id s21576_90197
closed s21576_90197
```
