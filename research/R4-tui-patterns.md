# R4 — TUI Interaction Patterns (PTY + Screen Snapshot)

> **Archived first-pass research** — superseded by [`../knowledge/sources/`](../knowledge/sources/); folded into [`../knowledge/tui-patterns/`](../knowledge/tui-patterns/README.md) (which still cites this doc). See [`README.md`](README.md). Kept for provenance.


Research date: 2026-07-07. Sources: live web research via codex (--search) + WebFetch of the
fzf man page and xterm ctlseqs. Cross-checked against manpages.

This document defines reusable interaction paradigms for driving interactive terminal programs
through a pseudo-terminal (PTY) while observing a rendered **screen snapshot** (the terminal grid
of cells: char + fg/bg/bold/reverse/underline attrs + cursor row/col + which buffer is active).

Guiding principle across ALL patterns: the highest-confidence "done" signal is **child process
exited** or **shell prompt returned**. Snapshot heuristics are confidence signals layered on top.
Bind recognition to **cursor row + cell attributes** wherever possible; pure text matching
misclassifies scrollback and echoed input.

---

## 0. Foundations: snapshot capture, key encoding, quiescence

### 0.1 Screen snapshot via terminal emulation
A PTY yields a byte stream, not a screen. To snapshot, feed bytes into a headless terminal emulator
that maintains a rows×cols cell grid.

Pipeline: `spawn child under PTY -> read master bytes -> decode UTF-8 + ANSI/VT100/xterm escapes ->
feed headless emulator -> snapshot visible buffer (each cell: char, fg, bg, bold, dim, italic,
underline, reverse, blink, hidden, strike, wide/continuation) -> cursor x/y from emulator state`.

Libraries:
| Stack | Library | Role |
|---|---|---|
| Python | `pyte` | in-memory VTxxx emulator. `Screen` = matrix w/ attrs; `Stream` parses escapes; `screen.cursor.x/.y`; `screen.display` = rendered text lines. https://pyte.readthedocs.io/en/0.4.1/ |
| Python | `pexpect`/`ptyprocess` | spawn/control under PTY; does NOT render full screen — pair with pyte. https://pexpect.readthedocs.io/en/stable/api/pexpect.html |
| Node | `node-pty` | PTY spawn + byte IO. https://github.com/microsoft/node-pty |
| Node | `@xterm/headless` | headless terminal state; `buffer.active.cursorX/cursorY`, `.type` = normal/alternate, `getLine()`. https://xtermjs.org/docs/api/terminal/interfaces/ibuffer/ , https://www.npmjs.com/package/@xterm/headless |
| Go | `hinshun/vt10x` | VT10x emulation backend. https://pkg.go.dev/github.com/hinshun/vt10x |
| Shell | `tmux capture-pane` | let tmux emulate; capture pane. |
| Shell | GNU `screen hardcopy` | dump displayed screen (+scrollback with -h). https://man7.org/linux/man-pages/man1/screen.1.html |

`tmux capture-pane` flags (https://man7.org/linux/man-pages/man1/tmux.1.html):
`-p` print to stdout; `-e` include SGR escape sequences; `-a` capture alternate screen; `-S start`
`-E end` line range (0=first visible, negative=history, `-`=extremes); `-J` join wrapped lines;
`-N` keep trailing spaces; `-T` ignore trailing empty; `-C` escape non-printables as octal;
`-M` capture pane-mode (copy mode) screen; `-q` quiet errors.
Cursor/buffer via format: `tmux display-message -p '#{cursor_x},#{cursor_y},#{alternate_on}'`
(`alternate_on` = 1 when alt screen active).

### 0.2 TUI vs line-oriented detection (alternate screen buffer)
Strongest signal a full-screen TUI launched = it entered the **alternate screen buffer**.
Detect in the byte stream (source: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html):
| Seq | Bytes | Meaning |
|---|---|---|
| ESC[?1049h | `\x1b[?1049h` | save cursor + switch to alt screen + clear (modern smcup) |
| ESC[?1049l | `\x1b[?1049l` | restore normal screen (rmcup) |
| ESC[?1047h/l | `\x1b[?1047h`/`l` | alt screen buffer on/off |
| ESC[?47h/l | `\x1b[?47h`/`l` | older alt screen on/off |
| ESC[2J | `\x1b[2J` | clear screen |
| ESC[H | `\x1b[H` | cursor home |
| ESC[?25l / ?25h | `\x1b[?25l`/`h` | hide / show cursor |
| ESC[?1h / ?1l | `\x1b[?1h`/`l` | DECCKM application / normal cursor keys |
| ESC[?1000h,1002h,1003h,1006h | mouse tracking modes | TUI wants mouse |
| ESC[?2004h | bracketed paste (weak signal alone) |

Heuristic:
```
if saw_alt_enter and not saw_alt_leave: mode = fullscreen_tui
elif many cursor-address + clears + cursor-hide: mode = screen-oriented
elif mostly printable + CR/LF + prompt regex: mode = line-oriented
else: mode = unknown/mixed
```
Use a real parser, not only regex: CSI can arrive as 8-bit `0x9b`, and escapes split across reads.

### 0.3 Quiescence / "output settled"
No universal "waiting for input" bit exists. Layer heuristics:
```
quiescent when:
  no PTY bytes for idle_ms
  AND visible snapshot hash unchanged for stable_ms
  AND no pending partial escape sequence
  AND (optional) recognizer says cursor is at a prompt/input area
```
Thresholds (idle_ms / stable_ms):
| Situation | idle | stable | note |
|---|---|---|---|
| Fast local shell cmd | 50-100 | 50-100 | |
| TUI redraw after keypress | 75-150 | 100-200 | avoid capturing mid-frame |
| Slow/network CLI | 250-500 | 250-500 | |
| Animated/progress UI | 500-1000 | require semantic condition | snapshot may never stabilize |
| Remote SSH/high latency | 500-2000 | 500-2000 | tune by RTT |

Snapshot hash:
```
cell_hash   = hash(char, fg, bg, bold, reverse, underline, cursor_here?)
screen_hash = hash(rows, cols, active_buffer, cursor_x, cursor_y, cursor_visible, all cell_hashes)
stable if screen_hash == previous for stable_ms
```
Exclude cursor **blink phase** from the hash, else a blinking cursor prevents stability.
Read loop:
```python
last_byte=last_change=now()
while True:
  data = read_pty(timeout=read_poll_ms)
  if data:
    last_byte=now(); emu.feed(data)
    if snapshot_hash()!=last_hash: last_change=now(); last_hash=snapshot_hash()
  if now()-last_byte>=idle_ms and now()-last_change>=stable_ms: break
```
pexpect: `child.expect([r'[$#] ', pexpect.TIMEOUT, pexpect.EOF], timeout=0.5)`; `expect_exact()`
for literal strings. For screen-oriented apps expect() alone is insufficient — pair with snapshot
stability, since visible state is assembled via cursor moves/overwrites.

### 0.4 Key encoding reference (bytes to WRITE to the PTY)
Source: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html ,
https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences
```
ESC=\x1b  CSI=\x1b[  SS3=\x1bO  CR=\r=0x0d  LF=\n=0x0a  DEL=\x7f  BS=\x08
```
Default Enter = **CR `\r` (0x0d)**, not `\n`. Raw-mode TUIs expect the terminal Enter sequence.
| Key | Bytes | | Key | Bytes |
|---|---|---|---|---|
| Enter | `\r` 0x0d | | Tab | `\t` 0x09 |
| Shift-Tab | `\x1b[Z` | | Escape | `\x1b` |
| Space | 0x20 | | Backspace | `\x7f` (or `\x08`) |
| Ctrl-C | `\x03` | | Ctrl-D (EOF) | `\x04` |
| Ctrl-N | `\x0e` | | Ctrl-P | `\x10` |
| Ctrl-L (redraw) | `\x0c` | | Ctrl-U (kill line) | `\x15` |
| Ctrl-Z | `\x1a` | | | |

Arrows — **normal cursor mode**: Up `\x1b[A` Down `\x1b[B` Right `\x1b[C` Left `\x1b[D`.
Arrows — **application cursor mode (DECCKM, after app sent ESC[?1h)**: Up `\x1bOA` Down `\x1bOB`
Right `\x1bOC` Left `\x1bOD`. IMPORTANT: many TUIs (vim, readline apps) enable application cursor
mode; if arrows do nothing, resend as SS3 (`\x1bO*`). Detect DECCKM by watching for ESC[?1h/l in
the output stream.
Home `\x1b[H` (or `\x1bOH`, or `\x1b[1~`); End `\x1b[F` (or `\x1bOF`, or `\x1b[4~`).
Insert `\x1b[2~`; Delete `\x1b[3~`; PageUp `\x1b[5~`; PageDown `\x1b[6~`.
F1-F4 `\x1bOP \x1bOQ \x1bOR \x1bOS` (older `\x1b[11~..14~`); F5 `\x1b[15~` F6 `\x1b[17~` F7 `\x1b[18~`
F8 `\x1b[19~` F9 `\x1b[20~` F10 `\x1b[21~` F11 `\x1b[23~` F12 `\x1b[24~`.
Modified keys add param: `CSI 15;2~`=Shift-F5, `;2`=Shift `;3`=Alt `;5`=Ctrl `;6`=Shift+Ctrl.

---

## Pattern A — LIST / MENU NAVIGATION (vim, k9s, lazygit, ncurses menus)

### Recognition (from snapshot)
- Multiple stacked rows of similar structure (a list), with **exactly one row visually
  distinguished** by one of:
  - **reverse video** (SGR 7): the selected row's cells have `reverse=true` (fg/bg swapped) —
    most common in ncurses/tview apps (k9s, lazygit panels).
  - **background color highlight**: selected row has a distinct bg color across full width.
  - **bold** (SGR 1) on the selected row.
  - a **caret/pointer glyph** at the row's left edge: `>`, `❯`, `›`, `*`, `→` in col 0-2.
- Cursor is often parked on or at the start of the highlighted row (tview/ncurses hide it).
- Not in an editable text field; content is a chooser, not free text.
- lazygit: multiple bordered panels, the *focused* panel has a colored/bold border and one
  highlighted line inside it. k9s: a table with a reverse-video current row + a top command bar.

Detector: find the row whose attribute run (reverse OR distinct bg OR bold) spans most of the
line width and is unique among sibling rows; OR the row starting with a pointer glyph. That row =
current selection. Track its index across snapshots to confirm movement.

### Drive
- Move down: `\x1b[B` (Down) — fallback `\x1bOB` (app mode) — or vim `j` (0x6a).
- Move up: `\x1b[A` (Up) — fallback `\x1bOA` — or vim `k` (0x6b).
- Page: PageDown `\x1b[6~`, PageUp `\x1b[5~`; or Ctrl-D/Ctrl-U in vim-like.
- Jump top/bottom: `g`/`G` (vim, lazygit, k9s), or Home `\x1b[H` / End `\x1b[F`.
- Confirm/activate: Enter `\r`.
- To reach target row N: read current selection index from snapshot, send Down/Up the delta count,
  re-snapshot to confirm the highlight moved by 1 each time (do NOT fire all keys blindly — verify
  per step, because wrap-around and filtered lists change the count).

### Done
- The highlighted-row index equals the target index (verified by snapshot) → then Enter.
- After Enter: the list disappears / a new screen loads / the selected value appears echoed / a
  detail view opens. If the same list with same selection persists after Enter, the item may be a
  submenu header (re-classify) or the app needs a different activate key.

---

## Pattern B — FUZZY SEARCH / FILTER (fzf-style incremental)
Source: fzf man page (WebFetch of man/man1/fzf.1).

### Recognition (from snapshot)
- A **prompt line** `> ` (default `--prompt`); the query the user types appears after it.
- An **info/match-count line** showing `X/Y` (matched/total), drawn from FZF_MATCH_COUNT /
  FZF_TOTAL_COUNT, on the left end of a horizontal separator line (`─` unicode / `-` with
  --no-unicode).
- A **pointer** on the current item: `▌` (unicode) or `>` (with --no-unicode), at the left of the
  current row.
- A **multi-select marker**: `┃` (unicode) or `>` (--no-unicode) on chosen rows.
- Layout: `default` = list rises from bottom, prompt/info at bottom; `reverse` = prompt/info at top,
  list below; `reverse-list` = list at top, prompt anchored at bottom.
- Behavioral tell: as you type a char, the visible list **narrows live** and the `X/Y` count drops.

### Drive (fzf default binds, from man page)
- Type query: send literal chars; list filters incrementally after each byte.
- Move down: Down `\x1b[B`, `ctrl-j` (0x0a is LF — fzf binds ctrl-j to `down`), `ctrl-n` `\x0e`
  (down-match; note: remapped to next-history when --history is set).
- Move up: Up `\x1b[A`, `ctrl-k` 0x0b, `ctrl-p` `\x10` (up-match; history-remapped as above).
- Accept current: Enter `\r` (action `accept`).
- Toggle multi-select: Tab `\t` (`toggle+down`), Shift-Tab `\x1b[Z` (`toggle+up`).
- Abort: Ctrl-C `\x03`, Ctrl-G `\x07`, Ctrl-Q `\x11`, or Esc `\x1b` (all bound to `abort`).
- Clear query: Ctrl-U `\x15`; backspace to delete chars `\x7f`.

Strategy to select a known item: type enough of its distinctive substring that `X/Y` shows a small
Y (ideally 1), verify the pointer is on the desired row, then Enter. For multiple: Tab each, then
Enter.

### Done
- fzf exits (process ends, alt screen leaves) and the chosen line(s) are printed to stdout /
  consumed by the calling command; shell prompt returns.
- On abort keys: fzf exits non-zero with no selection.
- Recognize completion: the fuzzy UI (prompt line + X/Y + pointer) disappears from the snapshot.

---

## Pattern C — PAGER (less / man / git log / more)
Sources: less(1) https://man7.org/linux/man-pages/man1/less.1.html ,
more(1) https://man7.org/linux/man-pages/man1/more.1.html ,
git core.pager https://git-scm.com/book/en/v2/Customizing-Git-Git-Configuration

### Recognition
High confidence:
- Bottom row starts with `:` at/near col 0 (less command prompt), optionally after a reverse-video
  cleared status line.
- Bottom row contains `(END)` (less, end of file).
- Status line shows filename + percent or byte/line position, e.g. `file.txt 37%`, `byte 123/456`.
- `more(1)` prompt: `--More--`, `--More--(37%)`, or `[Press space to continue, 'q' to quit.]`.
- In alternate screen buffer; content static until keys arrive.
Medium: bottom status line is reverse-video/standout; body looks like read-only text with cursor on
bottom command line; `man` first line like `GIT-LOG(1)` and section headers NAME/SYNOPSIS.
Avoid false positives: a literal `:` in output isn't enough — require bottom-row position AND no
shell prompt. A lone `(END)` in body text isn't enough unless in the status area.

### Drive
- Advance page: Space 0x20, or `f` 0x66, or PageDown `\x1b[6~`.
- Back page: `b` 0x62, or PageUp `\x1b[5~`.
- Line scroll: `j`/Down `\x1b[B`, `k`/Up `\x1b[A`.
- Top/bottom: `g` 0x67 / `G` 0x47.
- Search: `/` + pattern + `\r` (e.g. `/error\r`); next `n` 0x6e; prev `N` 0x4e.
- Quit: `q` 0x71.

### Done
- To consume all output: page (Space) until status shows `(END)`, then `q`.
- To just exit: send `q`; done when process exits / shell prompt returns / alt screen leaves.
- If no `(END)` after K page advances but process exits/prompt returns, treat as done.
- less in follow mode / live input: `(END)` may not be final — require prompt/process exit.

---

## Pattern D — CONFIRM / YES-NO DIALOG
Sources: apt-get(8) https://manpages.ubuntu.com/manpages/focal/man8/apt-get.8.html ; ssh host-key.

### Recognition
High confidence — last 1-3 lines contain a question + bracket/paren choice:
`[y/N]`, `[Y/n]`, `(y/n)`, `(yes/no)`, `[yes/no]`, `[Y/n]?`, `[y/N]?`, plus verbs like
`Proceed?`, `Continue?`, `Are you sure?`, `Do you want to continue?`, `Overwrite?`, `Remove?`.
Examples: apt `Do you want to continue? [Y/n]`; ssh `Are you sure you want to continue connecting
(yes/no/[fingerprint])?`; installer `Proceed ([Y]es/[N]o)?`.

### Default-choice detection (capitalization convention)
- `[Y/n]`, `(Y/n)`, `[YES/no]` → **default YES** → bare Enter accepts.
- `[y/N]`, `(y/N)`, `[yes/NO]` → **default NO** → bare Enter rejects.
- `[Y]es/[N]o` alone may only show hotkeys, not a default. `(yes/no)` has no default unless one is
  capitalized or text says so. `Ok to proceed? (y)` usually accepts only `y`.

### Drive
- Accept: `y\r` (0x79 0x0d); full form `yes\r` when prompt says `(yes/no)` / "type yes".
- Reject: `n\r` (0x6e 0x0d) or `no\r`.
- Default: bare Enter `\r`.
- Abort: Ctrl-C `\x03`.
Decision rule:
```
if prompt has "(yes/no" or "type yes" or ssh host-key form: accept="yes\r"
elif explicit default exists and desired==default: send "\r"
elif desired==yes: "y\r" else "n\r"
```

### Done
- Prompt line disappears / new output follows / process exits / shell prompt returns.
- If the SAME prompt remains after 300-500 ms, the answer wasn't accepted: retry once with `yes\r`
  (if prompt is yes/no form), or re-parse (maybe there is no default and bare Enter was ignored).

---

## Pattern E — PROGRESS / SPINNER WAITING
Sources: curl progress meter https://curl.se/docs/manpage.html ,
https://everything.curl.dev/cmdline/progressmeter.html ; apt/dpkg; npm.

### Recognition (needs SUCCESSIVE snapshots, not one)
Spinner: same row updates every 50-250 ms, cycling frames:
- ASCII `| / - \`
- braille `⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`
- often with text: `Installing`, `Resolving`, `Fetching`, `Loading`.
Progress bar: `45%`/`100%`; `[#####     ]`, `████░░░`, `====>   `; counters `12/40`, `3.4 MB/10 MB`.
curl meter header: `% Total % Received % Xferd Average Speed Time Time Time Current` then redrawn
numeric rows. apt/dpkg: `Reading package lists... Done`, `Unpacking...`, `Setting up...`.
Carriage-return redraw tell (if raw stream available): repeated `\r` without `\n`, or `\r\x1b[K`
(CR + erase-line) = strong progress-line signal. Snapshot-only tell: one active line changes while
row count stays stable and cursor stays on that row.

### Drive
Usually **send nothing**. Optional: abort Ctrl-C `\x03`. Send Enter only if you detect an actual
input prompt (not ordinary progress).

### Done — heuristic stack (highest confidence first)
1. Child process exits. 2. Shell prompt returns. 3. Completion word appears: `Done`, `Complete`,
`Finished`, `Success`, `installed`, `up to date`, `added N packages`, `Reading package lists...
Done`.
4. Percent hits 100% AND progress line disappears / non-progress output follows.
5. Bar full AND no redraw for 500-1000 ms.
6. curl reaches 100% then command exits (don't rely on 100% alone; may still verify/flush).
Snapshot-stability fallbacks:
- Quick CLI: stable 750-1500 ms + no spinner → done **only if** prompt/exit also seen.
- Package install/download: stable 3-5 s ≠ done by itself → "quiet wait" unless prompt/exit/word.
- Long network/build: stable 10-30 s = "possibly hung", not done.
Recommended: poll 100 ms while active. Spinner "active" if any frame changes ≥2× within 1 s.
Progress "active" if percent/counter/bar changes within 5 s. "maybe-hung" if no change for 30 s
(npm/curl) or 60-120 s (apt/build), process alive, no prompt, no spinner/progress updates.

### Still-working vs waiting-for-input vs hung
- Waiting for input: last line has `?`, `[y/N]`, `(yes/no)`, `Password:`, `Username:`,
  `Press ENTER`, `Press any key`, `Select`; cursor visible at end of prompt; stable ≥500 ms; alive.
- Still working: spinner frames change / counters change / new log lines / cursor hidden or CR
  redraw; no question/input vocabulary on final lines.
- Hung: no change past threshold, no input prompt, process alive, no exit, last line mid-operation.

---

## Pattern F — FORM / FIELD INPUT (dialog, whiptail, debconf forms)
Sources: dialog(1) https://linux.die.net/man/1/dialog ; whiptail https://www.mankier.com/1/whiptail ;
debconf https://manpages.debian.org/bullseye/debconf-doc/debconf.7.en.html

### Recognition
Strong signals:
- Box-drawn/ASCII frame with buttons `<Ok>`, `<Cancel>`, `[ OK ]`, `[Cancel]`.
- Multiple label+editable-value rows aligned in columns (`Name: ____`, `Version: 1.0.0`).
- Cursor is inside/after an input field, NOT at a shell prompt.
- Focused field has reverse-video/highlight/colored bg, or cursor lands within its bounds.
- Underline runs / blank boxed regions / fixed-width value cells.
- Bottom buttons reachable by Tab: OK / Cancel / Help / Back / Next.
Detectors (regex, applied to de-ANSI'd text but keep cursor/attrs):
```
buttons     (?i)(<\s*ok\s*>|<\s*cancel\s*>|\[\s*ok\s*\]|\[\s*cancel\s*\])
field_label ^\s*[A-Za-z][A-Za-z0-9 _./-]{1,30}\s*[:=]\s*\S?.*$
checkbox    \[[ xX]\]|\([ xX]\)
radio       \([* ]\)|<[* ]>
```
Require ≥1 of: 2+ field_label rows + buttons; cursor inside underlined/boxed region; reverse-video
field + nearby label.

### Drive
- Fill focused field: safest generic = Backspace `\x7f` × N to clear default, then type text.
  (Ctrl-U `\x15` clears line only in readline-style widgets, not universal.)
- Next field: Tab `\t`, or Down `\x1b[B`, or dialog Ctrl-N `\x0e`.
- Prev field: Shift-Tab `\x1b[Z`, or Up `\x1b[A`, or dialog Ctrl-P `\x10`.
- Within field: Left `\x1b[D` Right `\x1b[C` Home `\x1b[H` End `\x1b[F` Backspace `\x7f`.
- Toggle checkbox/radio: Space `\x20`.
- Submit: Enter `\r`. If focus is in a multiline edit box, Tab to OK first, then Enter.
State machine: identify focused field (cursor/highlight) → fill → Tab/Shift-Tab to target →
Space for checkbox/radio → Tab to OK/Next → Enter → wait until frame gone / screen changes.

### Done
Done: form/dialog frame disappears and prior output resumes / next wizard page replaces it /
process exits / new prompt (shell, npm, REPL) appears / no OK/Cancel/field remains.
Stuck/error: same field still focused after Enter; validation text
`(?i)(required|invalid|must|cannot|error|try again)`; screen hash unchanged after submit (ignoring
cursor blink).

---

## Pattern G — REPL SESSION (prompt detection, multi-line continuation)
Sources: Python sys.ps1/ps2 https://docs.python.org/3/library/sys.html ;
Node REPL https://nodejs.org/learn/command-line/how-to-use-the-nodejs-repl ;
GDB https://ftp.gnu.org/old-gnu/Manuals/gdb/html_chapter/gdb_17.html ;
IPython https://ipython.readthedocs.io/en/stable/config/details.html ;
IRB https://ruby-doc.org/3.4.1/stdlibs/irb/IRB.html ; LLDB https://lldb.llvm.org/use/tutorial.html

### Recognition — prompt regexes (match on CURSOR ROW)
```
Python primary        ^>>> $
Python continuation   ^\.\.\. $
IPython primary       ^In \[\d+\]:\s?$
IPython continuation  ^\s*\.\.\.:\s?$|^\s*\.\.\.\s*$
Node primary          ^> $
Node continuation     ^\.\.\. $
GDB primary           ^\(gdb\) $
LLDB primary          ^\(lldb\) $
IRB primary           ^irb\([^)]*\):\d{3}(?::\d+)?> $
generic fallback      ^\([A-Za-z0-9_.-]+\) $
```
A REPL is READY when: cursor is on the same row as a primary prompt (immediately after prompt text,
or after echoed input following it); the prompt is the last non-empty visible line; screen stable
≥1 poll. Do NOT treat output lines as prompts unless the cursor is on/after that line (output may
contain `>>>`, `...`, `>`). Cursor-row binding is mandatory.

### Drive
- Send command: `bytes(command) + \r`. Wait for primary prompt to reappear on cursor row = done.
- Exit: Ctrl-D (EOF) `\x04`; Node `.exit\r`; Python `exit()\r`/`quit()\r`; GDB/LLDB `quit\r`.
Multi-line continuation: if cursor row matches a continuation prompt, the REPL wants more input —
send the next line + `\r`, don't wait for output yet. Python compound statement: send blank line
`\r` at `... ` to finish the block. Example:
```
"for i in range(3):\r"  -> wait /^... $/
"    print(i)\r"        -> wait /^... $/
"\r"                    -> wait /^>>> $/   (blank line ends block)
```
Node function: `function f() {\r` → `... `, `return 1\r` → `... `, `}\r` → `> `.

### Done
Command done when: primary prompt regex reappears on cursor row after echo/output AND stable 1 poll
AND not currently at a continuation prompt. NOT done when: cursor row = secondary prompt, output
still appending, or debugger inferior is running with no `(gdb)`/`(lldb)` visible.
Edge cases: GDB pager `--Type <RET> for more, q to quit, c to continue--` → send Space or `c`, keep
waiting for `(gdb) `. Allow caller to override prompt regexes (GDB `set prompt`).

---

## Pattern H — WIZARD / MULTI-STEP INSTALLER FLOW
Sources: Vite https://vite.dev/guide/ ; CRA https://create-react-app.dev/docs/getting-started/ ;
npm package.json https://docs.npmjs.com/files/package.json/ ; debconf; dialog; whiptail; git rebase
https://git-scm.com/docs/git-rebase

### Recognition
- One current question/prompt at a time; screen advances after each Enter.
- Step markers: `Step 1 of 4`, `1/4`, `(1 of 4)`.
- Modern JS-CLI glyphs: `? Project name: › vite-project`, `◇ Select a framework:`, `◆ ...`, `› React`.
- npm init sequence: `package name:`, `version:`, `description:`, `entry point:`, `test command:`,
  `git repository:`, `keywords:`, `author:`, `license:`.
- debconf/dialog pages: framed box titled `Package configuration` + buttons `<Ok> <Yes> <No>
  <Cancel> <Back> <Next>`. Menu page: vertical choices, one highlighted. Yes/no page: question +
  Yes/No buttons.
Regexes:
```
step_counter     (?i)\b(step\s*)?\d+\s*(of|/)\s*\d+\b
npm_init         ^\s*(package name|version|description|entry point|test command|git repository|keywords|author|license):(?:\s*\([^)]*\))?\s*$
text_prompt      ^\s*[?◇◆]\s+.+:\s*(?:›\s*)?.*$
dialog_buttons   (?i)(<\s*yes\s*>|<\s*no\s*>|<\s*ok\s*>|<\s*next\s*>|<\s*back\s*>)
completion       (?i)\b(done|success|completed|installed|created|scaffolding project|happy hacking|now run|wrote to)\b
validation_error (?i)\b(required|invalid|already exists|not empty|must|please choose|try again|error)\b
```
Classify current step: text-prompt (cursor after `:`/`› default`, no dominant list); menu-select
(multiple choices, one highlighted or prefixed `> ❯ › * (*)`, prompt says Select/Choose/Which);
yes/no (question + `(y/N)`/`(Y/n)`/`[y/N]`/yes/no); dialog page (framed + OK/Cancel/Next/Back/Yes/No).

### Drive
- Text prompt: type answer + `\r`; accept default: `\r`; clear default: Backspace × N (or Ctrl-U in
  inquirer/readline) then answer + `\r`.
- Menu select: Down `\x1b[B`/Up `\x1b[A` to target, then `\r`; sometimes Space `\x20` toggles first.
- Yes/no: `y\r`/`n\r`, or Left/Right `\x1b[D`/`\x1b[C` between buttons then Enter.
- dialog/whiptail menu: Up/Down to item, Space for checklist/radio, Tab `\t` to OK, Enter.
Examples: npm init — answer each field or Enter for defaults; final `Is this OK? (yes)` → `\r` or
`yes\r`, done at `Wrote to ... package.json`. create-vite — `? Project name: ›` → `my-app\r`;
`Select a framework` → arrows + `\r`; `Select a variant` → arrows + `\r`; done at `Done. Now run:`
or `Scaffolding project in ...`. git rebase -i is NOT a wizard screen — it opens $EDITOR with a
todo buffer (`^pick [0-9a-f]{7,40} .+`, `# Commands:` help); drive via editor (vim `:wq\r`, nano
Ctrl-O `\x0f` Enter Ctrl-X `\x18`); done at `Successfully rebased and updated ...`.

### Advance detection (per step)
1. Hash normalized screen BEFORE sending. 2. Send answer + submit. 3. Poll until one of: screen
hash changes materially / question regex changes / step counter increments / prompt disappears /
completion regex appears. 4. Same question + validation_error → stuck/invalid. 5. Same question, no
error, after timeout → retry submit once, then surface ambiguous state.

### Done
Completion regex appears (`done|success|completed|installed|created|happy hacking|now run|wrote to`),
OR app exits + shell prompt returns, OR final install output stable + prompt returns, AND no
wizard/dialog/menu/question remains. NOT done while: current prompt active, focus on OK/Next after
validation msg, spinner/gauge updating, apt/dpkg still `Setting up`/`Unpacking`/`Processing
triggers`.

---

## Cross-cutting implementation notes / gotchas
1. **Cursor-row binding beats text matching.** Prompt strings (`>`, `:`, `...`, `[y/N]`) appear in
   scrollback and echoed input; only trust them when the cursor is on/after that row and the screen
   is quiescent.
2. **Application cursor mode (DECCKM).** Watch for `ESC[?1h`/`ESC[?1l` in output. When app mode is
   on, arrows must be sent as SS3 (`\x1bOA`..`\x1bOD`), not CSI (`\x1b[A`..). If arrow navigation
   has no effect, switch encoding and retry.
3. **Enter = CR `\r` (0x0d)**, not LF. Raw-mode TUIs expect the terminal Enter byte.
4. **Verify movement step-by-step** in lists/menus; never fire N arrow keys blindly — wrap-around,
   live-filtering, and variable row heights make blind counts wrong. Re-snapshot after each key.
5. **Blinking cursor** must be excluded from the stability hash or the screen never "settles".
6. **Escapes split across PTY reads** and 8-bit CSI (`0x9b`) require a real VT parser, not regex on
   raw bytes, to build the grid. Regex is a fast side-channel only.
7. **"Done" is layered**: process-exit / shell-prompt-return are ground truth; snapshot heuristics
   (completion words, `(END)`, prompt reappearance) are confidence signals. Never rely on 100%/
   stability alone for long ops.
8. **Confirm retries**: `y\r` may be rejected where `yes\r` is required (ssh, some installers);
   retry with the full word if the prompt persists.
9. **tmux capture-pane -e** gives you SGR-annotated text cheaply if you don't want to embed a full
   emulator; `-a` grabs the alternate screen, `display-message #{alternate_on}` tells you if a TUI
   is active.
