# Notable TUI Frameworks & Polished TUI Apps — Raw Survey

> Research date: 2026-07-08. Every entry carries its real URL. Techniques extracted
> via WebFetch of primary sources (repo / author writeup / official docs) where the
> page was fetchable. Where a page was only marketing-level, that is flagged and the
> technique is drawn from the fetched primary doc that *did* contain it.

Master list source: **rothgar/awesome-tuis** — https://github.com/rothgar/awesome-tuis
(the canonical "List of projects that provide terminal user interfaces"; other
awesome-tuis repos are forks of this one).

---

## FRAMEWORKS / LIBRARIES

### Textual (Python)
- Repo: https://github.com/Textualize/textual
- Deep-dive (primary, author Will McGugan): https://textual.textualize.io/blog/2024/12/12/algorithms-for-high-performance-terminal-apps/
- **Standout technique — "switch the primitive" + segment compositor.** Textual does
  NOT treat the terminal as a 2D char grid (breaks on double-width CJK/emoji). Everything
  is a **Segment** (string + style), inherited from Rich, converted to ANSI only at the
  very end. The **compositor** merges overlapping widgets' segment lists into one
  non-overlapping list, line by line:
  1. **Find the cuts** — scan for every offset where any segment list begins/ends; record
     those boundary offsets.
  2. **Apply the cuts** — split each segment list at those offsets into equal-width pieces
     ("chops") so nothing overlaps.
  3. **Discard chops** — only the top-most chop at each position is visible; occluded ones
     are thrown away.
  4. **Combine** — merge surviving top chops into the final line.
- **Spatial Map** (`_spatial_map.py`) — classic game-dev grid bucketing to discard
  off-screen widgets in ~constant time regardless of widget count. Tile size **100 cols ×
  20 lines**; dict maps grid coord -> list of widgets overlapping that tile. Scrolling
  1000 widgets costs ~same as 8. Structure is "very cacheable" (no recompute while
  scrolling). Both `_compositor.py` and `_spatial_map.py` are open source and the author
  invites reuse.
- Also does partial updates (redraw only the changed region, e.g. a button color flip).

### Rich (Python)
- Repo: https://github.com/Textualize/rich
- Sister lib to Textual; the **Segment (string+style) model** and Renderable protocol
  that Textual's compositor is built on. Rich text, tables, syntax highlighting, progress
  bars — the rendering substrate.

### Ratatui (Rust) — actively-maintained fork of tui-rs
- Repo: https://github.com/ratatui/ratatui  (older URL: tui-rs-revival/ratatui)
- Rendering docs (primary): https://www.ratatui.rs/concepts/rendering/under-the-hood/
  and https://ratatui.rs/concepts/rendering/
- **Standout technique — immediate-mode + double-buffer diff.** UI is recreated from
  scratch every frame (`Terminal::draw(|frame| ...)`). Two `Buffer`s of `Cell`s; a `Cell`
  is "the smallest renderable unit" (~a pixel), holding a **1-wide string symbol + style**
  (fg, bg, modifiers) stored *separately* from the symbol (so embedded ANSI in a cell
  string is NOT interpreted — you must convert via e.g. `ansi-to-tui` first). Each frame:
  wipe current buffer, let widgets draw into it, **diff current vs previous buffer** to
  emit only changed cells, then **swap buffers**. Because all widgets write one shared
  buffer, later widgets overwrite earlier ones — render order matters. (The concrete
  diff/cursor-move code lives in `buffer.rs`/`terminal.rs`, not the doc page.)
- v0.30 added more precise buffer-diff options, Block shadows, Canvas/Chart filled areas.

### Bubble Tea + Lip Gloss + Bubbles (Go) — Charm
- Repo: https://github.com/charmbracelet/bubbletea  (Lip Gloss:
  https://github.com/charmbracelet/lipgloss)
- Architecture deep-dive (primary, generated from repo):
  http://www.factory.ai/open-source-wikis/bubbletea?page=overview/architecture.md
- **Standout technique — The Elm Architecture + single-consumer event loop.** Model with
  `Init() Cmd`, `Update(Msg)`, `View()`. `Msg = uv.Event`; `Cmd = func() Msg` (a command
  is just a func returning a message). MANY producers (input reader, signal/resize
  listener, command goroutines) feed **one `chan Msg`**; the event loop is the **only
  consumer** — this is what makes updates deterministic. Commands run in their own
  goroutines (so `time.Tick` etc. don't block); `BatchMsg` fans out concurrently,
  `sequenceMsg` runs sequentially; panics recovered so a bad command can't wreck the
  terminal.
- **Renderer** (`cursedRenderer`): cell-buffered, draws into a `uv.ScreenBuffer` double
  buffer, then `TerminalRenderer.flush` **diffs frames and writes minimal ANSI** —
  tracks **dirty lines**, uses cursor-move optimizations (hard tabs, backspace, `\n`
  mapping). A **60 Hz ticker** flushes pending output (render is throttled, not per-update).
  Frames can be wrapped in **DEC mode 2026 synchronized output** to avoid tearing. Alt
  screen / mouse mode / colors are declarative per-frame `View` fields. All writes
  serialized through one mutex-guarded buffer.

### prompt_toolkit (Python)
- Repo: https://github.com/prompt-toolkit/python-prompt-toolkit
- Powers IPython, ptpython, etc. Full-screen apps + advanced line editing, syntax
  highlighting, multiline, autocompletion. Layout engine with containers/controls; its own
  renderer that diffs a screen buffer and emits minimal escape sequences. (Listed in
  awesome-tuis under Python libraries.)

### blessed (Node.js) / Ink (Node.js — React)
- Ink repo: https://github.com/vadimdemedes/ink  (blessed:
  https://github.com/chjj/blessed)
- **Ink standout — React reconciler for the terminal.** Uses **Yoga** (Flexbox layout
  engine) to lay out components, a React reconciler to diff the virtual DOM, and only
  repaints changed output. Used by many CLIs (Gatsby, Jest watch, etc.). blessed is the
  older widget/curses-style lib; ink is the modern React-model approach.

### notcurses (C/C++)
- Repo: https://github.com/dankamongmen/notcurses
- Render model (man pages): https://manpages.ubuntu.com/manpages/resolute/man3/notcurses_render.3.html
- **Standout technique — ncplanes + pile rasterization + pixel blitters.** You draw onto
  a stack of virtual **ncplanes** (z-ordered); nothing shows until `ncpile_rasterize` /
  `notcurses_render` flattens the pile to the physical display. Supports **pixel graphics
  blitters**: sixel, the Kitty graphics protocol, and Unicode
  quadrant/sextant/braille cell-subdivision blitters for sub-cell "pixel" resolution on
  any terminal. Aims to beat/replace ncurses for multimedia + high-FPS TUIs.

### FTXUI (C++), Spectre.Console (.NET), tview/tcell (Go), urwid (Python)
- FTXUI: https://github.com/ArthurSonzogni/FTXUI — functional/declarative C++ TUI,
  compose components with operators, flexbox-like layout.
- Spectre.Console: https://github.com/spectreconsole/spectre.console — .NET, Rich-inspired
  (tables, live displays, prompts, canvas).
- tview: https://github.com/rivo/tview  (on tcell: https://github.com/gdamore/tcell) —
  Go widget library; tcell is the low-level cell/screen abstraction (event model +
  screen diffing) that k9s and others build on.
- urwid: https://github.com/urwid/urwid — long-standing Python console UI lib.

---

## IMAGE / GRAPHICS IN THE TERMINAL

### Kitty Terminal Graphics Protocol
- Spec (primary): https://sw.kovidgoyal.net/kitty/graphics-protocol/
- **Standout technique — APC escape wrapper + base64 chunking + z-layering.** Command form:
  `<ESC>_G<control k=v,k=v>;<base64 payload><ESC>\`. APC is used because most emulators
  ignore unknown APC codes (safe). Formats via `f`: `f=32` RGBA (default), `f=24` RGB,
  `f=100` PNG; raw needs `s`(width)/`v`(height). Remote data is **chunked <=4096 bytes,
  each non-final chunk a multiple of 4**, with `m=1` continuation / `m=0` final; only the
  first chunk carries full control keys. Mediums (`t`): `d` inline, `f` file, `t` temp
  file (path must contain `tty-graphics-protocol`), `s` shared memory. Placement: `a=T`
  transmit+show, or transmit with id `i=` then place with `a=p`. Sub-cell offset via
  `X`/`Y`; target size in cells via `c`/`r` (aspect preserved if one given). **z-index**
  via `z`: **negative z draws under text** (text-over-image); ties broken by lower image
  id. Query support: `a=q` then `<ESC>[c` — if you get DA reply but no query reply, no
  graphics support. Get pixel/cell size: `TIOCGWINSZ` ioctl, or `<ESC>[14t` ->
  `<ESC>[4;h;w t`, or the more precise per-cell `<ESC>[16t`.

### chafa — image -> Unicode/ANSI character art
- Repo: https://github.com/hpjansson/chafa  | Home: https://hpjansson.org/chafa/
- **Standout technique — glyph coverage matching + perceptual color space.** Combines
  Unicode symbols from multiple selectable ranges (block, half/quadrant, braille, sextants)
  and picks the glyph whose on/off coverage best approximates the source cell's pixels,
  choosing fg/bg colors per cell. Supports **RGB and DIN99d color spaces** for improved
  perceptual color picking (DIN99d = perceptually uniform). Output targets: truecolor /
  256 / 16 / FG-BG, plus **sixel and Kitty** graphics modes. (NOTE: repo README + home
  page are high-level; the exact coverage-bitmap comparison + dithering math lives in the
  C source/API docs, not the fetched pages — flag for deeper source dig if needed.)

### Braille-graph rendering (used by btop, bottom, ytop, mapscii)
- Reference: https://nigeltao.github.io/blog/2024/blue-noise-braille-art.html
- **Standout technique — Braille Patterns block (U+2800..U+28FF) as a 2x4 monochrome
  pixel matrix per cell.** Each cell becomes 8 sub-pixels (2 wide x 4 tall); set the bit
  for each "lit" sub-pixel and add the offset to U+2800 to get the glyph. This is how
  system monitors draw smooth line graphs at 2x4 resolution per character cell. (Downside
  seen in issues: needs a font with proper braille glyph spacing or graphs look uneven.)

---

## SHOWCASE APPS

### fzf — command-line fuzzy finder (Go)
- Repo: https://github.com/junegunn/fzf
- Algorithm deep-dive (primary, visualized): https://timothya.com/learning/fzf
- **Standout technique — FuzzyMatchV2 = modified Smith-Waterman DP.** Treats matching as
  an optimization: of all in-order threadings of pattern through text, which scores highest
  (no mismatches allowed, only where the gaps go). Recurrence per cell:
  `s1 = H[i-1][j-1] + scoreMatch + bonus` (consume pattern char);
  `s2 = H[i][j-1] + (inGap ? gapExt : gapStart)` (skip text char); `H = max(s1,s2,0)`.
  **Constants:** match **+16**, gap-start **-3**, gap-extension **-1** (affine gap ->
  prefers one long gap over scattered ones). **Bonuses:** word boundary **+8**, after
  whitespace/BOS **+10**, after `/ , : ; |` delimiter **+9**, camelCase/letter->digit
  **+7**, consecutive-run **+4**, first-char **x2**. Boundary bonus is calibrated to be
  cancelled by ~8 chars of gap (keeps it a fuzzy finder, not an acronym matcher). A
  parallel **C matrix** tracks run length so `foob` prefers `foobar` over `foo-bar`.
  Four phases: (1) ASCII gate finds feasible min/max window; (2) compute bonuses +
  feasibility check; (3) forward-fill DP table (int16, cap M<=1000 else fall back to O(n)
  greedy V1); (4) backtrace through H (+C) to recover matched positions.

### lazygit — terminal UI for git (Go)
- Repo: https://github.com/jesseduffield/lazygit
- Deep-dive series (primary, contributor): https://oliverguenther.de/2021/04/lazygit-an-introduction-series/
- **Standout technique — multi-panel focus model on gocui.** Built on **gocui** (jroimartin
  fork), not Bubble Tea. Layout is a set of **views/panels** (files, branches, commits,
  stash, main) navigable with arrows; each panel keeps its own cursor/selection state.
  Context-driven keybindings change meaning per focused panel. Renders git output into
  panel views; the "main" panel shows diffs/logs contextual to the selection in the side
  panels.

### k9s — Kubernetes cluster TUI (Go)
- Repo: https://github.com/derailed/k9s
- **Standout technique — tview-based real-time watch + resource views.** Built on
  **tview/tcell**. Continuously **streams/watches** cluster state and refreshes tables in
  real time; surfaces failing pods, live logs, resource usage. Includes **XRay** (tree view
  of resource relationships) and **Pulses** (dashboard of cluster health). Command-mode
  navigation (`:pods`, `:deploy`) like vim. (Repo README is feature-level; the watch/refresh
  is the standout interaction pattern.)

### gitui — blazing-fast git TUI (Rust)
- Repo: https://github.com/extrawurst/gitui
- **Standout technique — async git on a background queue keeps UI at 60fps.** Built on
  Ratatui/tui-rs. Heavy git operations (diffs, logs, status) run **asynchronously off the
  render thread** via a job queue so the UI never blocks (explicit design goal: stay
  responsive on huge repos where lazygit/tig stall). Uses libgit2 (git2-rs). Syntax-
  highlighted diffs.

### btop / btop++ — resource monitor (C++)
- Repo: https://github.com/aristocratos/btop
- **Standout technique — braille-based graphs + own draw layer.** Draws animated CPU/mem/
  net/disk graphs using the **Braille Patterns block (2x4 sub-pixels per cell)** for smooth
  high-resolution curves, truecolor gradients, mouse support, and a custom terminal draw
  layer. Successor to bashtop/bpytop rewritten in C++ for speed.

### htop — interactive process viewer (C)
- Repo: https://github.com/htop-dev/htop
- **Standout technique — ncurses meters + per-column sortable process table.** Classic
  ncurses app; color meter bars for CPU/mem/swap, tree view of processes, mouse + keyboard,
  incremental search/filter. The reference point for "process monitor TUI."

### bottom — graphical process/system monitor (Rust)
- Repo: https://github.com/ClementTsang/bottom
- **Standout technique — Ratatui widgets + braille graphs, htop-meets-graphs.** Zoomable
  time-series graphs (braille), configurable widget grid layout, mouse + vim keys.

### yazi — async terminal file manager (Rust)
- Repo: https://github.com/sxyazi/yazi
- Design blog (primary): https://yazi-rs.github.io/blog
- **Standout technique — fully async (Tokio) with a two-tier task scheduler.** Everything
  time-consuming (I/O + CPU) is an async task off the render thread. Tasks split into
  **macro** (heavy, e.g. large file copy; 10 workers default) and **micro** (small/urgent,
  e.g. mime detection, image preload, dir size; 5 workers) — "when big cores are idle they
  help with micro tasks," plus 3 priority levels (low/normal/high) to preempt. **Chunked
  directory loading** (streams 100k-file dirs progressively; only re-reads changed files).
  **Discardable tasks**: fast navigation aborts in-flight previews (Tokio `abort` for I/O;
  atomic per-line `ticket` for CPU highlighting; interruptible Lua plugin tasks). **Render
  batching** merges multiple actions into one render; progress bars render independently.
  Highlighting bounded to visible window (e.g. only first 10 lines on a 10-line terminal;
  kills `jq` after 10 lines). **Two-pass image preview**: pre-downscale to a cached lossy
  image, then downscale again to fit on select; video/PDF pre-converted to images. Output
  via Kitty / inline / sixel; **stdout locked only after image data prepared** (no perf
  hit, prevents corruption during fast nav); can partially erase preview so popups don't
  overlap, then redraw.

### glow — markdown renderer/reader (Go) — Charm
- Repo: https://github.com/charmbracelet/glow
- **Standout technique — styled markdown via glamour + Bubble Tea browser.** Renders
  markdown to styled terminal output using **glamour** (ANSI stylesheet themes), with a
  Bubble Tea scrollable pager/file-browser. Shows what Charm's stack looks like end-to-end.

### slumber — terminal HTTP/REST client (Rust)
- Repo: https://github.com/LucasPickering/slumber
- **Standout technique — Ratatui + declarative YAML request collections.** TUI HTTP client
  built on Ratatui; define/execute/share configurable requests from YAML, template values,
  view formatted responses. A clean example of a modern Ratatui component-based app with
  async request execution.

### atuin — magical shell history (Rust)
- Repo: https://github.com/atuinsh/atuin  | Deep-wiki: https://deepwiki.com/atuinsh/atuin
- **Standout technique — SQLite-backed history + Ratatui full-screen fuzzy search + E2E
  sync.** Replaces the shell history file with a **SQLite DB** recording rich context (cwd,
  host, session, exit code, duration, timestamp). Ctrl-R opens a Ratatui full-screen search
  UI with filter modes (host/dir/session/global) and fuzzy/prefix search over the DB.
  Optional end-to-end-encrypted cross-machine sync.

---

## awesome-tuis TOP-STARRED ENTRIES (grouped)
Source: https://github.com/rothgar/awesome-tuis (raw README fetched)

- **Libraries:** textual, rich, urwid (Py); bubbletea, tview, tcell (Go); ratatui (Rust);
  FTXUI (C++); Spectre.Console (.NET); ink (Node).
- **File managers:** yazi, ranger, nnn, broot, lf, superfile.
- **Git:** lazygit, gitui, tig, delta.
- **System monitors:** btop, bottom, htop, glances, bandwhich, gping.
- **Dashboards/clusters:** k9s, lazydocker, ctop, gh-dash, wtf, dive.

(URLs for each in the sections above / in the awesome-tuis README.)
