# Raw Findings: Agent Engineering for Driving / Replicating CLIs

Meta-layer knowledge base. Every fact carries a SOURCE URL (paper / canonical repo / official docs).
Collected 2026-07-08. NOTE: codex dispatcher (claude-codex-subagent) was verified working but the
upstream provider (pigcode.org) returned HTTP 403 "insufficient balance" on all 3 runs, so these
findings were gathered via direct WebSearch/WebFetch of authoritative sources per the fallback plan.

Dispatch evidence (all 3 failed identically):
  ERROR: unexpected status 403 Forbidden: 预扣费额度失败, 用户剩余额度: $0.0037, 需要预扣费额度: $0.0117
  ... url: https://cdn.pigcode.org/v1/responses

=====================================================================================
SECTION A — DRIVING INTERACTIVE CLIs VIA PTY
=====================================================================================

## A1. pexpect (Python, POSIX pty)
- spawn defaults to BYTES mode. Passing `encoding=` (e.g. spawn('cmd', encoding='utf-8'))
  switches to a unicode interface: strings sent are encoded, bytes received are decoded before
  return, and expect()/expect_exact() patterns must then also be unicode.
  SOURCE: https://pexpect.readthedocs.io/en/stable/api/pexpect.html
- `codec_errors` (default 'strict') controls handling of undecodable bytes: 'strict' | 'ignore' |
  'replace'. Critical for non-UTF8 PTY output.
  SOURCE: https://pexpect.readthedocs.io/en/stable/api/pexpect.html
- spawnu is legacy: in Pexpect 3.x unicode was a separate spawnu class; as of 4.0 spawn provides
  both bytes and unicode via encoding=. Use encoding= now.
  SOURCE: https://pexpect.readthedocs.io/en/stable/api/pexpect.html
- expect() matches REGEX patterns. pexpect.EOF and pexpect.TIMEOUT are two special patterns that
  are NOT regular expressions. before/after hold text around the match.
  SOURCE: https://pexpect.readthedocs.io/en/stable/overview.html
- pexpect.spawn and pexpect.run() are NOT available on Windows — they rely on Unix pseudoterminals.
  On Windows only PopenSpawn exists (no pty), and it "is not a direct replacement for spawn."
  SOURCE: https://pexpect.readthedocs.io/en/stable/overview.html
- readline returns CR/LF line endings "because this is what the pseudotty device returns"; getecho/
  setecho are "Not supported on platforms where isatty() returns False" — i.e. tty-ness gates echo.
  SOURCE: https://pexpect.readthedocs.io/en/stable/api/pexpect.html

## A2. node-pty (Microsoft)
- forkpty(3) bindings; "fork processes with pseudoterminal file descriptors" returning a terminal
  object allowing reads and writes.
  SOURCE: https://github.com/microsoft/node-pty
- API: pty.spawn(file, args, options) where options = {name:'xterm-color', cols:80, rows:30, cwd,
  env}. Methods/events: onData((data)=>...), write('ls\r'), resize(cols, rows). Extra options:
  handleFlowControl, flowControlPause, flowControlResume.
  SOURCE: https://github.com/microsoft/node-pty
- On Windows it uses the ConPTY API; winpty support has been REMOVED and it now requires Windows 10
  1809+. On Unix it uses forkpty(3).
  SOURCE: https://github.com/microsoft/node-pty

## A3. pywinpty (Windows)
- Supports BOTH the native ConPTY interface and the previous fallback winpty (rprichard) library.
  SOURCE: https://github.com/andfoy/pywinpty
- High-level: PtyProcess.spawn('python'); then proc.write(...), proc.readline(), proc.isalive().
  Low-level: PTY(cols, rows) exposing spawn(), read(), write(), set_size(cols, rows), isalive().
  SOURCE: https://github.com/andfoy/pywinpty
- Built with Rust bindings (PyO3/Maturin); MIT; pip install pywinpty. PyPI framing: "PyWinpty allows
  creating and communicating with Windows processes that receive input and print outputs via
  console input and output pipes."
  SOURCE: https://pypi.org/project/pywinpty/2.0.1/

## A4. tmux programmatic control
- send-keys `-l` "disables key name lookup and processes the keys as literal UTF-8 characters."
  Named keys (e.g. 'C-a', 'NPage', Enter/C-m) are sent by name; unrecognized strings sent as chars.
  `-H` "expects each key to be a hexadecimal number for an ASCII character."
  SOURCE: https://man.openbsd.org/tmux
- capture-pane: `-p` sends output to stdout (else to a buffer). `-e` "output includes escape
  sequences for text and background attributes." `-S`/`-E` set start/end line (0 = first visible
  line; negatives reach into history/scrollback). `-J` "preserves trailing spaces and joins any
  wrapped lines; -J implies -T." `-t target-pane` selects the pane.
  SOURCE: https://man.openbsd.org/tmux
- Control mode: tmux `-C` starts control mode; "Given twice (-CC) disables echo."
  SOURCE: https://man.openbsd.org/tmux

=====================================================================================
SECTION B — ESCAPE-SEQUENCE / TTY GOTCHAS (ground truth = the bytes)
=====================================================================================

## B1. Application Cursor Keys (DECCKM), private mode 1
- Set = CSI ? 1 h  = "Application Cursor Keys (DECCKM), VT100."  Reset = CSI ? 1 l = Normal.
  SOURCE: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
- Arrow/cursor keys CHANGE encoding by mode. Normal (CSI) vs Application (SS3):
    Cursor Up    = CSI A (ESC [ A)   vs   SS3 A (ESC O A)
    Cursor Down  = CSI B             vs   SS3 B
    Cursor Right = CSI C             vs   SS3 C
    Cursor Left  = CSI D             vs   SS3 D
    Home = CSI H / SS3 H ; End = CSI F / SS3 F
  So a driver sending "ESC [ A" for Up will FAIL against a full-screen app that enabled DECCKM
  (it expects "ESC O A"). This is the classic arrow-key gotcha.
  SOURCE: https://xorg.freedesktop.org/archive/X11R7.0/doc/ctlseqs.txt

## B2. Alternate Screen Buffer
- CSI ? 1049 h = "Save cursor as in DECSC ... switch to the Alternate Screen Buffer, clearing it
  first." CSI ? 1049 l = "Use Normal Screen Buffer and restore cursor as in DECRC."
  SOURCE: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
- Older variants: ?1047 = "Use Alternate Screen Buffer" (l clears screen first if in alt);
  ?47 = "Use Alternate Screen Buffer" (no cursor save). Behavior subject to titeInhibit resource.
  SOURCE: https://xorg.freedesktop.org/archive/X11R7.0/doc/ctlseqs.txt
- Implication: when a TUI enters alt-screen, scrollback/history is a separate buffer; a naive
  capture of the primary buffer sees stale content.

## B3. Bracketed Paste, private mode 2004
- CSI ? 2004 h = "Set bracketed paste mode, xterm." CSI ? 2004 l = reset.
  SOURCE: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
- (Widely documented behavior: when enabled, pasted text is wrapped ESC[200~ ... ESC[201~ so the
  app distinguishes paste from typing — the specific wrapper wording was truncated in the fetched
  ctlseqs section, so treat wrapper bytes as needing a secondary confirm before relying on them.)

## B4. isatty / not-a-tty behavior
- pexpect: echo control (getecho/setecho) is "Not supported on platforms where isatty() returns
  False" — programs branch on tty-ness.
  SOURCE: https://pexpect.readthedocs.io/en/stable/api/pexpect.html
- General consequence (well-known): non-tty stdout is fully buffered (not line-buffered) and many
  tools suppress color when not a tty — this is WHY driving via a PTY (not a pipe) matters. Anchor
  for buffering/tty semantics: POSIX termios + stdio.
  SOURCE: https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/termios.h.html

## B5. CRLF vs LF translation (termios)
- c_oflag controls output treatment. OPOST = "Post-process output" (master switch). ONLCR = "Map
  NL to CR-NL on output" (XSI). c_iflag ICRNL = "Map CR to NL on input." These flags produce the
  CR/LF you see from a PTY vs raw LF.
  SOURCE: https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/termios.h.html

=====================================================================================
SECTION C — REVERSE-ENGINEERING BUNDLED / PACKED APPS (recover UI constants)
=====================================================================================

## C1. strings (GNU binutils)
- `-n`/`--bytes=min-len` prints displayable sequences ">= min-len characters long"; default minimum
  length is 4. Sequences terminate at control chars (newline, CR) but not tab.
  SOURCE: https://sourceware.org/binutils/docs/binutils/strings.html
- `-e`/`--encoding` selects encoding: 's'=7-bit (default), 'S'=8-bit, 'b'=16-bit big-endian,
  'l'=16-bit LITTLE-endian, 'B'/'L'=32-bit. "'l' and 'b' apply to ... Unicode UTF-16/UCS-2." On
  Windows binaries you MUST use `-e l` to recover UTF-16LE strings (the default 7-bit misses them).
  SOURCE: https://sourceware.org/binutils/docs/binutils/strings.html
- `-a`/`--all` scans the whole file regardless of sections.
  SOURCE: https://sourceware.org/binutils/docs/binutils/strings.html

## C2. ripgrep (rg) on binaries
- Default: "a file is considered binary if and only if it contains a NUL byte"; on detection
  "searching stops" and rg warns it stopped prematurely.
  SOURCE: https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md
- `-a`/`--text` = "Search binary files as if they were plain text" — "completely disables all binary
  detection." (Warns high memory on very large files.)
  SOURCE: https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md
- `--binary` = binary mode: does NOT stop at first NUL; continues until EOF or a match — "discover
  matches in all files, but avoid having binary data dumped into your terminal."
  SOURCE: https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md
- `-o`/`--only-matching` prints only matched text; `-U`/`--multiline` = "Permit matches to span
  multiple lines." (-P/--pcre2 exists per rg man page but not in GUIDE.md — verify separately.)
  SOURCE: https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md
- Tip: binary detection can vary by search strategy; use --no-mmap for consistent results.
  SOURCE: https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md

## C3. Node.js Single Executable Applications (SEA)
- SEA injects a blob (bundled script) into the node binary; "During start up, the program checks if
  anything has been injected. If the blob is found, it executes the script in the blob."
  SOURCE: https://nodejs.org/api/single-executable-applications.html
- Workflow: sea-config.json ({main, output, useCodeCache, useSnapshot, assets}) ->
  `node --experimental-sea-config` produces a .blob -> copy the node binary -> inject with
  `npx postject ... NODE_SEA_BLOB sea-prep.blob --sentinel-fuse
  NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2`. PE binaries store it as resource NODE_SEA_BLOB;
  ELF as a note; Mach-O as a section in NODE_SEA segment. The fuse sentinel's last char is flipped
  to '1' to mark injection. (Newer: `node --build-sea sea-config.json`.)
  SOURCE: https://nodejs.org/api/single-executable-applications.html
- useCodeCache=true precompiles main to V8 code cache (note: import() does not work then);
  useSnapshot runs main at BUILD time and requires v8.startupSnapshot.setDeserializeMainFunction().
  Both must be false for cross-platform SEAs.
  SOURCE: https://nodejs.org/api/single-executable-applications.html
- RE consequence: the embedded JS lives verbatim in the blob region (resource/note/section named
  NODE_SEA_BLOB) — locate that region, carve it, then read the bundled JS. For pkg/nexe the JS is
  similarly embedded (V8 snapshot / virtual FS).

## C4. Reading minified / bundled JS (Ink/React TUI bundles)
- Source Map format (ECMA-426 / v3): generated code links to a map via `//# sourceMappingURL=...`
  (consumers accept both //# and //@; generators emit //#). The `mappings` field is Base64 VLQ
  encoded. JSON fields: version (always 3), file, sourceRoot, sources, sourcesContent (inlined
  ORIGINAL source text — gold for RE), names, mappings.
  SOURCE: https://tc39.es/ecma426/
- If a .map with sourcesContent is shipped, you recover the ORIGINAL source, not just prettified
  minified code. Consume with the `source-map` npm module.
  SOURCE: https://www.npmjs.com/package/source-map
- mappings VLQ decoding (the hard part) is handled by jridgewell/sourcemap-codec.
  SOURCE: https://github.com/jridgewell/sourcemap-codec

## C5. Finding UI constants (ANSI/colors/keybindings) in a bundle
- The ESC byte is 0x1B (decimal 27). In JS string literals it is commonly encoded as , \x1b,
  \033 (octal), or the literal control byte. Grep a minified bundle for these encodings to find
  ANSI sequences / color tables / layout constants. ESC introduces CSI as ESC [ and SS3 as ESC O
  (see B1). SOURCE (byte + CSI/SS3 semantics): https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

=====================================================================================
SECTION D — GROUNDING vs HALLUCINATION / ACI DESIGN / MEASURE-GROUND-TRUTH
=====================================================================================

## D1. SWE-agent: Agent-Computer Interface (ACI)
- Paper: "SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering." Authors:
  John Yang, Carlos E. Jimenez, Alexander Wettig, Kilian Lieret, Shunyu Yao, Karthik Narasimhan,
  Ofir Press. arXiv:2405.15793. Core claim: a custom ACI "significantly enhances an agent's ability
  to create and edit code files, navigate entire repositories, and execute tests." pass@1: 12.5% on
  SWE-bench and 87.7% on HumanEvalFix, "far exceeding" non-interactive LMs.
  SOURCE: https://arxiv.org/abs/2405.15793
- Four concrete ACI design features (verbatim from official docs):
  1. GUARDRAIL / edit linting: a linter runs on edit commands and they "do not let the edit command
     go through if the code isn't syntactically correct."
  2. Purpose-built file viewer (not `cat`): "this file viewer works best when displaying just 100
     lines in each turn," with scroll + in-file search.
  3. Concise directory search: it must "succinctly list the matches" (each file with >=1 match);
     more per-match context "proved to be too confusing for the model."
  4. Informative feedback on empty output: "Your command ran successfully and did not produce any
     output." (never leave the agent guessing whether the action worked).
  SOURCE: https://swe-agent.com/latest/background/aci/
- General ACI thesis (official): "designing simple LM-centric commands and feedback formats to make
  it easier for the LM to browse the repository, view, edit and execute code files."
  SOURCE: https://swe-agent.com/latest/background/

## D2. ReAct (reasoning + acting)
- Paper: "ReAct: Synergizing Reasoning and Acting in Language Models," Yao et al., arXiv:2210.03629.
  Core idea: interleave reasoning traces with actions so the model grounds reasoning in real
  environment observations, reducing hallucination/error propagation and improving interpretability.
  SOURCE: https://arxiv.org/abs/2210.03629

## D3. Terminal-Bench (ground-truth measurement for terminal agents)
- Stanford x Laude Institute benchmark: "a dataset of tasks, and an execution harness that connects
  a language model to our terminal sandbox." Each task = an English instruction + a TEST SCRIPT that
  verifies success + an "oracle" reference solution. Scoring is pass/fail by whether tests pass.
  Runs in an isolated Docker sandbox; beta with ~100 tasks; run via `tb run`.
  SOURCE: https://github.com/laude-institute/terminal-bench
- Site: https://terminal-bench.ai
- Measure-ground-truth embodiment: success is decided by executing verification tests against actual
  system state, NOT by the agent's self-report. This is the discipline codified as a benchmark.

## D4. "Measure ground truth, don't approximate" — synthesis
- The ACI empty-output message (D1.4) and edit-lint guardrail (D1.1) are concrete instances: the
  interface reports the ACTUAL result of each action rather than letting the agent assume.
  SOURCE: https://swe-agent.com/latest/background/aci/
- ReAct (D2) is the algorithmic form: observe real output between thoughts instead of predicting it.
  SOURCE: https://arxiv.org/abs/2210.03629
- Terminal-Bench (D3) is the evaluation form: verify via executed tests on real state.
  SOURCE: https://github.com/laude-institute/terminal-bench
