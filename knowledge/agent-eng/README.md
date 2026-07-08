# Agent Engineering Knowledge Graph

Cross-linked knowledge base on driving/replicating CLIs with agents. Every entry is grounded in the mined digest (`D:/Project/SmartCLI/knowledge/sources/raw-agent-eng.md`) and carries an authoritative **Source:** URL. Links between entries are wiki-style `[[filename-slug]]`.

## A. Driving interactive CLIs via PTY

- [[pty-vs-pipe]] — spawn under a real pseudoterminal; pipes are block-buffered and kill color.
- [[pexpect-encoding]] — pexpect is bytes by default; pass `encoding='utf-8'` + `codec_errors`.
- [[pexpect-no-windows-pty]] — pexpect's PTY spawn is POSIX-only; Windows gets non-PTY `PopenSpawn`.
- [[node-pty]] — canonical Node driver: `spawn`, `onData`, `write('ls\r')`, `resize`.
- [[node-pty-windows-conpty]] — modern node-pty is ConPTY-only on Windows (needs Win10 1809+).
- [[pywinpty]] — the Windows pexpect: dual ConPTY/winpty backend, `PtyProcess.spawn`.
- [[tmux-send-keys-literal]] — `-l` sends literal UTF-8, bypassing key-name lookup.
- [[tmux-capture-pane]] — `-p -e -J -S` snapshots ground-truth pane state with color + scrollback.
- [[tmux-control-mode]] — `-CC` = machine-parseable control mode with echo disabled.

## B. Escape-sequence / TTY gotchas (the bytes ARE the ground truth)

- [[application-cursor-keys-deckm]] — DECCKM (`CSI ?1h`) flips arrows to SS3 `ESC O A`; the #1 arrow bug.
- [[alternate-screen-buffer]] — `CSI ?1049h` switches to the cleared alt buffer TUIs live in.
- [[bracketed-paste]] — mode 2004 wraps pasted input so it differs from typed input.
- [[crlf-termios]] — `OPOST`/`ONLCR`/`ICRNL` control CR-LF translation on the PTY.
- [[isatty-branching]] — programs drop color and full-buffer when stdout isn't a tty.

## C. Reverse-engineering bundled/packed apps

- [[strings-utf16le]] — `-e l` catches Windows UTF-16LE UI strings the default mode misses.
- [[ripgrep-binary-search]] — `-a`/`--binary`/`--no-mmap` to grep packed exes without NUL truncation.
- [[node-sea-blob]] — carve embedded JS from the `NODE_SEA_BLOB` region marked by the fuse sentinel.
- [[source-maps]] — a shipped `.map` recovers real source via `sourcesContent`.
- [[hunt-the-esc-byte]] — grep `0x1B` / `\x1b` / `\033` to find ANSI + layout constants in minified TUIs.

## D. Grounding vs hallucination / ACI / measure-ground-truth

- [[aci-thesis]] — the Agent-Computer Interface, not the model alone, drives success (SWE-agent).
- [[aci-design-rules]] — four verbatim SWE-agent surface rules (guardrail, 100-line viewer, terse search, empty-output message).
- [[react]] — interleave reasoning with actions grounded in real observations.
- [[terminal-bench]] — success judged by executed test scripts in Docker, never self-report.
