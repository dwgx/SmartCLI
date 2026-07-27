# SmartCLI — launch copy (ready to paste)

Copy for the two-phase launch (see `NEXT-STEPS.md §C`). **Numbers fact-checked
against the live code 2026-07-27:** 30 fx effects · 8 themes · 17 tui-ui widgets ·
8 drive-tui recipes. **Before posting, re-run `python -m fx list` and
`python -m ui widgets` and take the live numbers** — counts drift, and a wrong
number in launch copy is the one error everybody checks. Links: repo
github.com/dwgx/SmartCLI · site https://dwgx.github.io/SmartCLI/ · docs
https://smartcli.readthedocs.io/ · PyPI `pip install smartcli-toolkit`.

**Rules baked in (from launch research):** no emoji walls, no
"revolutionary/seamless/autonomous", no unverified platform claims, concrete
numbers only, and always link `LIMITATIONS.md` (listing your own edges is the
strongest anti-"AI-slop" signal). Do NOT post the ignite copy (C4/C5) before the
lazygit proof reel is live — it is (`showcase/drive-lazygit.gif`).

---

## Positioning sentence (the one-liner everything hangs on)

**Lead with the problem, not the architecture.** Earlier drafts of this file
opened with "three agent skills over one pluggable PTY + pyte core", which asks
the reader to learn three concepts before they know what the thing does. The
problem sentence lands in one read:

> AI agents can't use interactive terminal programs. Give an agent `vim`, `htop`
> or `lazygit` and it's blind: it can pipe bytes, but it can't see which menu row
> is highlighted or know whether its keystroke landed. SmartCLI keeps a live cell
> grid of what the terminal actually renders — cursor, reverse-video selection,
> alternate screen — so an agent drives full-screen curses TUIs the way a person
> watching the screen would. Runs on Windows (ConPTY) as well as POSIX.

Proof to lead with (all reproducible by the reader, which is the point):
- `python examples/drive_vim.py` drives the **real vim binary** — opens a file,
  appends a line, saves — then verifies the **filesystem**, not the screen. No
  `sleep()` anywhere; every wait is a screen-state predicate.
- We don't assert that the screen model is right, we **measure** it: identical
  bytes to a real tmux pane and to our model, grids diffed cell by cell. Three
  suites (35 curated cases; a three-way check that only trusts a behaviour when
  **tmux *and* GNU screen agree**; a generative VT fuzz). That found and fixed
  **12 emulation bugs**.
- The most telling one: `pyte` implements **no alternate screen buffer**, so
  before 0.2.0 driving vim didn't just look wrong — **the file was never saved**,
  because a driver that can't see the alt screen mistimes the `:wq`. The agent
  believed it had edited a file that was untouched on disk. Run the demo against
  `smartcli-toolkit==0.1.8` to watch it happen.

Rebuttal-proofing (say these when probed):
- **vs pexpect:** pexpect regex-matches the byte stream and can't tell which row
  is highlighted; SmartCLI matches the *screen*. pexpect also has no Windows PTY.
- **vs Textual / rich / TTE:** those *build* TUIs; SmartCLI *drives and perceives*
  other people's TUIs. Different verb.
- **vs ht / pilotty / termwright:** those are POSIX/Unix-socket-only; SmartCLI is
  an in-process library that runs natively on Windows too, and adapts arrow keys
  to the app's live DECCKM cursor-key mode (SS3 vs CSI) — a correctness edge the
  POSIX-first crowd skips.
- **"isn't this just pyte?"** pyte is the cell-grid emulator we build on, and it
  has real gaps for this use case — no alt-screen, no SGR sub-parameters, several
  cursor/insert-delete divergences from a real terminal. Finding and fixing those
  (with tmux and GNU screen as referees) is a substantial part of what SmartCLI
  is. The differential suites are in `tests/_diff_*.py` if someone wants to check.
- **"why not screenshots + a vision model?"** Cost and determinism. A structured
  cell grid is exact, diffable, hashable for change detection, and free; it also
  feeds the rendering side of the project. Vision is none of those.
- **honest limits, say them first:** real tmux is now verified (3.6b) but the
  interactive DECCKM probe still wants a real-host run; two behaviours are
  recorded as genuinely undefined because tmux and GNU screen disagree; the
  project is young (July 2026) and the API can still move before 1.0.

## Channel intelligence (checked against the live repos 2026-07-27)

Scouted before writing anything, because a rejected PR costs more than a skipped
channel. What was actually found:

| Channel | Stars | Verdict |
|---|---|---|
| **punkpeye/awesome-mcp-servers** | 91k | **PR OPENED** — [#11022](https://github.com/punkpeye/awesome-mcp-servers/pull/11022). Best fit: SmartCLI *is* an MCP server. Its CONTRIBUTING explicitly invites automated agents (`🤖🤖🤖` in the title fast-tracks review), so the PR was filed transparently as agent-prepared, owner-reviewed. |
| **rothgar/awesome-tuis** | 20k | **SKIPPED — category mismatch.** Every section lists TUI *applications*, and Libraries/Python is TUI-building frameworks (Rich, Textual, urwid). SmartCLI *drives other people's* TUIs — different verb. Forcing it in invites a close plus a bad first impression with the maintainer. |
| **hesreallyhim/awesome-claude-code** | 51k | **OWNER-ONLY, by their rules.** CONTRIBUTING: recommendations must use the web issue form, "it is **not** possible to submit using the `gh` CLI", and "recommendations must be created by human beings" — submitting otherwise "risks being restricted from interacting with this repository". Also states the honest ordering: *get users first, then submit*. Do this yourself, later. |
| **agarrharr/awesome-cli-apps** | 20k | Plausible but weak fit (it lists end-user CLI apps). Low priority. |

**The lesson worth keeping:** fit beats reach. A 91k-star list that matches the
category is worth more than three 20k lists that don't, and the mismatched ones
carry real downside.

## PHASE 1 · C2 — awesome-list PR text (durable, low-risk; open these anytime)

For each: fork, add one line in the right category, follow the list's format, link
the site. Suggested entry line (adjust bullet style per list):

Each entry leads with the capability, not the architecture:

- **awesome-cli-apps** (Shell/CLI tools):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - Drive and perceive interactive terminal programs (vim, htop, lazygit) through a PTY with a live cell-grid screen model; also a terminal-effects engine and cell-accurate widgets.`
- **awesome-tuis** (libraries / tooling):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - Drive and perceive other programs' TUIs: pyte cell-grid model with screen-state waits, verified against real tmux; Windows ConPTY + POSIX.`
- **awesome-claude-code / agent-skill lists** (skills):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - Lets an agent drive full-screen terminal programs (vim, htop, lazygit) by reading the actual screen; ships as an MCP server and three agent skills.`
- **awesome-python** (Terminal / CLI):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - Drive interactive terminal programs through a PTY + pyte screen model, with waits that react to the rendered screen instead of sleeping.`
- **awesome-mcp-servers** (the highest-fit list — it is literally an MCP server):
  `[SmartCLI](https://github.com/dwgx/SmartCLI) - Drive interactive terminal programs (vim, htop, lazygit) from any MCP client: start a session, send keys, wait on screen state, read the rendered cell grid.`

PR title: `Add SmartCLI` · PR body: one sentence (the positioning line) + the
GIF/site link + "MIT, on PyPI". Check each list's CONTRIBUTING before opening.

---

## PHASE 2 · C4 — Show HN

**Title** (≤80 chars, no hype words, leads with the capability):
> Show HN: SmartCLI – let an AI agent drive vim, htop and lazygit by reading the screen

Alternates if that reads long:
> Show HN: SmartCLI – agents that drive full-screen TUIs by reading the cell grid
> Show HN: I gave AI agents eyes and hands for interactive terminal programs

**First comment — post it within a minute of submitting.** HN readers judge a
Show HN by the author's first comment more than by the README.

> Agents handle line-based REPLs fine, but point one at a full-screen curses app — vim, htop, k9s, lazygit, an ncurses installer — and it goes blind. pexpect regex-matches the byte stream, so it cannot tell you which menu row is highlighted, and it has no Windows PTY. The usual fallback is `sleep 2 && hope`.
>
> SmartCLI keeps a live cell grid of what the terminal actually renders, so an agent can ask "which row is reverse-video selected", "where is the cursor", "is this the alternate screen" — and every wait is a predicate on screen state rather than a sleep. Pluggable backend: ConPTY/pywinpty on Windows, POSIX pty elsewhere.
>
> The part I'd actually like feedback on is how the screen model is verified, because I didn't trust myself to assert it. Identical bytes go to a real tmux pane and to the model, and the two cell grids are diffed cell by cell: 35 curated cases, a three-way check that only accepts a behaviour when tmux *and* GNU screen agree, plus a generative fuzz over random VT sequences. That found 12 emulation bugs I would never have thought to look for.
>
> The worst one is a good illustration of why this matters. `pyte`, the emulator underneath, implements no alternate screen buffer at all — so driving vim didn't merely look wrong, the file was **never saved**: a driver that cannot see the alt screen mistimes the `:wq`. The agent believed it had edited a file that was untouched on disk. `examples/drive_vim.py` drives the real vim binary and then checks the filesystem, not the screen; run it against `smartcli-toolkit==0.1.8` and you can watch it fail.
>
> Honest scope: young project (July 2026), API can still move before 1.0. CI is a 3-OS matrix; real tmux 3.6b is verified, but the interactive DECCKM/SS3-arrow probe still wants a real-host run, and two behaviours are recorded as genuinely undefined because tmux and GNU screen disagree with each other. Those are in LIMITATIONS.md rather than hand-waved. It also ships a terminal-effects engine and a cell-accurate widget layer, but driving is the part I think is interesting.
>
> Repo: github.com/dwgx/SmartCLI (MIT) · `pip install smartcli-toolkit` · also an MCP server, so it plugs into Claude Code / Cursor / VS Code directly.

**If it gets traction, the follow-up comments to have ready** (see the
rebuttal-proofing block at the top of this file for "vs pexpect", "isn't this just
pyte", "why not screenshots + vision"):

- *"Does it work with <my TUI>?"* — Give them the two-line recipe rather than a
  yes: `smartcli-tui start --cmd "<their app>"` then `snapshot`. Ask them to paste
  the snapshot if it looks wrong; a real failing case from a stranger's app is the
  most valuable thing that can come out of a launch.
- *"How is this different from tmux send-keys + capture-pane?"* — That is a
  reasonable baseline and worth conceding: it works, and it is what the
  Terminal-Bench adapter builds on. The differences are that it needs tmux (no
  Windows), it gives you text with no attribute/selection information, and it has
  no readiness primitives — you are back to sleeping.
- *"Why not just use ht / pilotty / termwright?"* — POSIX-only, and mostly
  socket-daemon shaped. SmartCLI is an in-process library that also runs on
  Windows, and it adapts arrow keys to the app's live DECCKM mode (SS3 vs CSI),
  which is the kind of thing that silently breaks curses navigation.
- **If someone reports a bug, fix it the same day and say so in the thread.** That
  single behaviour converts more skeptics than any amount of copy.

**Timing:** submit Tue–Thu, 08:00–10:00 US Eastern. Be at a keyboard for the
following three hours — an unanswered first question is what kills a Show HN.

## PHASE 2 · C4 — Reddit r/commandline (visual angle)

**Title:** `SmartCLI: a pyte-backed toolkit that drives interactive TUIs (lazygit/less/htop) and renders terminal effects`

**Body:**
> Built a Python toolkit that models the terminal as a live `pyte` cell grid instead of a byte stream, so it can perceive what a full-screen TUI is actually showing (highlighted row, cursor, alt-screen) and drive it step by step. The GIF is it driving a real lazygit session on Linux.
>
> It also ships an effects engine (30 effects / 8 themes — solarsystem, donut, fire, rain, all rendered through the project's own pipeline, no screen recorder) and 17 cell-accurate UI widgets, since the same screen model feeds both perceiving and drawing. Runs on Windows (ConPTY) and Linux.
>
> MIT, `pip install smartcli-toolkit`, live playground and all the GIFs: dwgx.github.io/SmartCLI. Known limits are in LIMITATIONS.md — curious what breaks on your setup.

*(r/Python variant: same body, lead with "pip install smartcli-toolkit" and the
pexpect/pyte framing; drop the effects emphasis.)*

## PHASE 2 · C4 — X / Twitter thread (agent-dev angle)

1/ Agents can drive `bash` and REPLs, then go blind the second you point them at htop, k9s, or lazygit. The output is a byte stream; the app is a screen. SmartCLI closes that gap.

2/ It keeps a live `pyte` cell grid of what the terminal renders — cursor, reverse-video selection, alt-screen — so the agent reads the *screen*, not raw bytes, and drives with perceive → act → wait → confirm. No blind sleeps. [lazygit GIF]

3/ Why not pexpect? pexpect regex-matches bytes, can't tell which menu row is selected, and has no Windows PTY. SmartCLI's backend is pluggable: ConPTY on Windows, POSIX pty on Linux. Different job from Textual/TTE too — those build TUIs, this drives them.

4/ Ships as 3 agent skills on one core: drive TUIs, render effects (30, all through its own pipeline), cell-accurate widgets (17). Live playground: dwgx.github.io/SmartCLI

5/ Honest scope: verified on Debian 13 + Windows/ConPTY + macOS (3-OS CI incl. real-PTY smoke); real tmux still unverified; remaining edges in LIMITATIONS.md. Early. MIT. `pip install smartcli-toolkit` · github.com/dwgx/SmartCLI

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

