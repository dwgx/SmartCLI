# SmartCLI — launch copy (ready to paste)

Copy for the two-phase launch (see `NEXT-STEPS.md §C`). **Numbers fact-checked
against the live code 2026-07-13:** 19 fx effects · 8 themes · 15 tui-ui widgets ·
8 drive-tui recipes · 2 stars. Links: repo github.com/dwgx/SmartCLI · site
https://dwgx.github.io/SmartCLI/ · PyPI `pip install smartcli-toolkit`.

**Rules baked in (from launch research):** no emoji walls, no
"revolutionary/seamless/autonomous", no unverified platform claims, concrete
numbers only, and always link `LIMITATIONS.md` (listing your own edges is the
strongest anti-"AI-slop" signal). Do NOT post the ignite copy (C4/C5) before the
lazygit proof reel is live — it is (`showcase/drive-lazygit.gif`).

---

## Positioning sentence (the one-liner everything hangs on)

> SmartCLI drives interactive terminal programs the way a person watching the
> screen would: it keeps a live `pyte` cell-grid model of what the terminal
> actually renders — cursor, reverse-video selection, alt-screen — so an agent
> can drive full-screen curses TUIs like htop, k9s, or lazygit, not just
> line-oriented REPLs, and it runs on Windows (ConPTY) as well as POSIX.

Rebuttal-proofing (say these when probed):
- **vs pexpect:** pexpect regex-matches the byte stream and can't tell which row
  is highlighted; SmartCLI matches the *screen*. pexpect also has no Windows PTY.
- **vs Textual / rich / TTE:** those *build* TUIs; SmartCLI *drives and perceives*
  other people's TUIs. Different verb.
- **vs ht / pilotty / termwright:** those are POSIX/Unix-socket-only; SmartCLI is
  an in-process library that runs natively on Windows too, and adapts arrow keys
  to the app's live DECCKM cursor-key mode (SS3 vs CSI) — a correctness edge the
  POSIX-first crowd skips.

## PHASE 1 · C2 — awesome-list PR text (durable, low-risk; open these anytime)

For each: fork, add one line in the right category, follow the list's format, link
the site. Suggested entry line (adjust bullet style per list):

- **awesome-cli-apps** (Shell/CLI tools):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - Drive interactive TUIs, design terminal effects, and render cell-accurate UIs — three agent skills over one pluggable PTY + pyte core.`
- **awesome-tuis** (libraries / tooling):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - pyte-backed toolkit to drive and perceive interactive TUIs (and render effects/widgets); Windows ConPTY + POSIX.`
- **awesome-claude-code / agent-skill lists** (skills):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - Three agent skills: drive interactive terminal programs, design terminal visual effects, and render tmux-safe UI frames.`
- **awesome-python** (Terminal / CLI):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - Drive interactive terminal programs through a PTY + pyte screen model; also a terminal-effects engine and cell-accurate widgets.`

PR title: `Add SmartCLI` · PR body: one sentence (the positioning line) + the
GIF/site link + "MIT, on PyPI". Check each list's CONTRIBUTING before opening.

---

## PHASE 2 · C4 — Show HN

**Title** (no hype words):
> Show HN: SmartCLI – give AI agents a pyte screen model to drive interactive TUIs

**First comment (author, post immediately after):**
> I kept hitting the same wall: agents can drive line-based REPLs fine, but the moment you point one at a full-screen curses app — htop, k9s, lazygit, an ncurses installer — it goes blind. pexpect regex-matches the byte stream and has no idea which menu row is highlighted, and it has no Windows PTY at all.
>
> SmartCLI keeps a live `pyte` cell grid of what the terminal actually renders, so the agent perceives the real screen (cursor position, reverse-video selection, alt-screen) and drives with a perceive → decide → act → wait → confirm loop instead of blind sleeps. Backend is pluggable: ConPTY/pywinpty on Windows, POSIX pty on Linux. It ships as three agent skills over that one core: drive (this), render terminal effects, and cell-accurate UI widgets.
>
> The GIF is it driving lazygit on Debian 13 end to end — navigating panels, opening a commit's diff, highlighting a branch, all by reading the screen grid. Honest scope: the POSIX backend is verified on Debian 13/Python 3.13 and Windows/ConPTY; macOS and real tmux are not yet verified, and there's a known edge where selection-only cursor moves can read as "stable" too early — all of that is in LIMITATIONS.md rather than hand-waved. It's early (2 stars); I'd genuinely like to hear where it breaks on your TUIs.
>
> Repo: github.com/dwgx/SmartCLI · `pip install smartcli-toolkit` · live effects + interactive playground: dwgx.github.io/SmartCLI

## PHASE 2 · C4 — Reddit r/commandline (visual angle)

**Title:** `SmartCLI: a pyte-backed toolkit that drives interactive TUIs (lazygit/less/htop) and renders terminal effects`

**Body:**
> Built a Python toolkit that models the terminal as a live `pyte` cell grid instead of a byte stream, so it can perceive what a full-screen TUI is actually showing (highlighted row, cursor, alt-screen) and drive it step by step. The GIF is it driving a real lazygit session on Linux.
>
> It also ships an effects engine (19 effects / 8 themes — solarsystem, donut, fire, rain, all rendered through the project's own pipeline, no screen recorder) and 15 cell-accurate UI widgets, since the same screen model feeds both perceiving and drawing. Runs on Windows (ConPTY) and Linux.
>
> MIT, `pip install smartcli-toolkit`, live playground and all the GIFs: dwgx.github.io/SmartCLI. Known limits are in LIMITATIONS.md — curious what breaks on your setup.

*(r/Python variant: same body, lead with "pip install smartcli-toolkit" and the
pexpect/pyte framing; drop the effects emphasis.)*

## PHASE 2 · C4 — X / Twitter thread (agent-dev angle)

1/ Agents can drive `bash` and REPLs, then go blind the second you point them at htop, k9s, or lazygit. The output is a byte stream; the app is a screen. SmartCLI closes that gap.

2/ It keeps a live `pyte` cell grid of what the terminal renders — cursor, reverse-video selection, alt-screen — so the agent reads the *screen*, not raw bytes, and drives with perceive → act → wait → confirm. No blind sleeps. [lazygit GIF]

3/ Why not pexpect? pexpect regex-matches bytes, can't tell which menu row is selected, and has no Windows PTY. SmartCLI's backend is pluggable: ConPTY on Windows, POSIX pty on Linux. Different job from Textual/TTE too — those build TUIs, this drives them.

4/ Ships as 3 agent skills on one core: drive TUIs, render effects (19, all through its own pipeline), cell-accurate widgets (15). Live playground: dwgx.github.io/SmartCLI

5/ Honest scope: verified on Debian 13 + Windows/ConPTY; macOS + tmux not yet; known edges in LIMITATIONS.md. Early (2 stars). MIT. `pip install smartcli-toolkit` · github.com/dwgx/SmartCLI

## PHASE 2 · C5 — Claude Code / agent-skill communities

> If you use Claude Code or another agent CLI: SmartCLI's `drive-tui` skill lets
> your agent drive interactive terminal programs it currently can't — arrow-key
> menus, pagers, installers, curses apps — by reading a pyte screen model instead
> of a byte stream. Drop the skill in (`/plugin marketplace add dwgx/SmartCLI`),
> or `pip install smartcli-toolkit` for the core. GIF is it driving lazygit.
> Windows + Linux. MIT. Known edges documented. github.com/dwgx/SmartCLI

---

## Launch-day checklist

1. Confirm live: site (200), PyPI page, the lazygit GIF renders on the repo front page.
2. Post Show HN (best: weekday ~09:00 ET). Post the author first-comment within a minute.
3. Cross-post r/commandline + r/Python (space them out, not simultaneous).
4. X thread.
5. C5 skill-community post.
6. **Be present the first few hours** — answer "does it work with my TUI?" with the
   perceive/act framing + LIMITATIONS workarounds; invite bug reports as engagement.
7. Do NOT overclaim under pressure. "It's early, tell me where it breaks" beats defending.

