# Pattern E — Progress / Spinner Waiting

Recognize a progress/spinner UI only from SUCCESSIVE snapshots (one active line changing while row count stays stable), and usually send nothing — distinguish still-working / waiting-for-input / hung before acting.

### Recognition (needs multiple snapshots)
Spinner: same row updates every 50-250 ms cycling frames:
- ASCII `| / - \`
- braille `⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`
- often with text `Installing`, `Resolving`, `Fetching`, `Loading`.

Progress bar: `45%`/`100%`; `[#####     ]`, `████░░░`, `====>   `; counters `12/40`, `3.4 MB/10 MB`. curl meter header `% Total % Received % Xferd Average Speed Time Time Time Current` then redrawn numeric rows. apt/dpkg `Reading package lists... Done`, `Unpacking...`, `Setting up...`.
Raw-stream tell: repeated `\r` without `\n`, or `\r\x1b[K` (CR + erase-line) = strong progress-line signal. Snapshot-only tell: one active line changes while row count is stable and cursor stays on that row.

### Drive
Usually **send nothing**. Optional abort Ctrl-C `\x03`. Send Enter only if you detect an actual input prompt, not ordinary progress.

### Done
Use the layered done-signal stack (see [[done-signal-layering]]). Poll 100 ms while active. Spinner "active" if any frame changes ≥2× within 1 s. Progress "active" if percent/counter/bar changes within 5 s. "maybe-hung" if no change for 30 s (npm/curl) or 60-120 s (apt/build), process alive, no prompt, no spinner/progress update.

### Still-working vs waiting-for-input vs hung
- Waiting for input: last line has `?`, `[y/N]`, `(yes/no)`, `Password:`, `Username:`, `Press ENTER`, `Press any key`, `Select`; cursor visible at end of prompt; stable ≥500 ms; alive.
- Still working: spinner/counters change / new log lines / cursor hidden or CR redraw; no question/input vocabulary on final lines.
- Hung: no change past threshold, no input prompt, process alive, no exit, last line mid-operation.

**Source:** curl progress meter https://curl.se/docs/manpage.html , https://everything.curl.dev/cmdline/progressmeter.html ; apt/dpkg and npm output vocabulary

**See also:** [[done-signal-layering]], [[quiescence-detection]], [[confirm-yes-no-dialog]], [[snapshot-stability-hash]]
