# Pattern C — Pager Navigation (less / man / more)

Recognize a pager by its bottom-row command prompt / status line, and drive it with page keys until `(END)` (to consume all output) or send `q` (to just exit).

### Recognition
High confidence:
- Bottom row starts with `:` at/near col 0 (less command prompt), optionally after a reverse-video cleared status line.
- Bottom row contains `(END)` (less, end of file).
- Status line shows filename + percent or byte/line position, e.g. `file.txt 37%`, `byte 123/456`.
- `more(1)` prompt: `--More--`, `--More--(37%)`, or `[Press space to continue, 'q' to quit.]`.
- In alternate screen buffer; content static until keys arrive.

Medium: bottom status is reverse-video/standout; body is read-only text with cursor on the bottom command line; `man` first line like `GIT-LOG(1)` + section headers NAME/SYNOPSIS.
Avoid false positives: a literal `:` in output is not enough — require bottom-row position AND no shell prompt. A lone `(END)` in body text is not enough unless in the status area.

### Drive
- Advance page: Space 0x20, `f` 0x66, or PageDown `\x1b[6~`.
- Back page: `b` 0x62, or PageUp `\x1b[5~`.
- Line scroll: `j`/Down `\x1b[B`, `k`/Up `\x1b[A`.
- Top/bottom: `g` 0x67 / `G` 0x47.
- Search: `/` + pattern + `\r` (e.g. `/error\r`); next `n` 0x6e; prev `N` 0x4e.
- Quit: `q` 0x71.

### Done
Consume all: page (Space) until status shows `(END)`, then `q`. Just exit: send `q`; done when process exits / prompt returns / alt screen leaves. If no `(END)` after K page advances but process exits/prompt returns, treat as done. less in follow mode: `(END)` may not be final — require prompt/process exit.

**Source:** less(1) https://man7.org/linux/man-pages/man1/less.1.html , more(1) https://man7.org/linux/man-pages/man1/more.1.html , git core.pager https://git-scm.com/book/en/v2/Customizing-Git-Git-Configuration

**See also:** [[key-encoding-reference]], [[alternate-screen-detection]], [[done-signal-layering]], [[cursor-row-binding]]
