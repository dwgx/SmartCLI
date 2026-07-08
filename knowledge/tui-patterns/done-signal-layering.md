# Done-Signal Layering

"Done" is layered: process-exit and shell-prompt-return are ground truth; snapshot heuristics are confidence signals layered on top. Never rely on 100% / stability alone for long operations.

Highest confidence first:
1. Child process exits.
2. Shell prompt returns.
3. Completion word appears: `Done`, `Complete`, `Finished`, `Success`, `installed`, `up to date`, `added N packages`, `Reading package lists... Done`.
4. Percent hits 100% AND progress line disappears / non-progress output follows.
5. Bar full AND no redraw for 500-1000 ms.
6. curl reaches 100% then the command exits (don't rely on 100% alone; may still verify/flush).

Snapshot-stability fallbacks are situation-dependent and weak on their own:
- Quick CLI: stable 750-1500 ms + no spinner → done **only if** prompt/exit also seen.
- Package install/download: stable 3-5 s is NOT done by itself → "quiet wait" unless prompt/exit/word.
- Long network/build: stable 10-30 s = "possibly hung", not done.

**Source:** primary/synthesized — layering guidance distilled in the project TUI-patterns research digest (`research/R4-tui-patterns.md`); the completion vocabulary (`Done`, `installed`, `up to date`, `added N packages`, `Reading package lists... Done`) derives from observed apt/dpkg/npm/curl output.

**See also:** [[quiescence-detection]], [[progress-spinner-waiting]], [[cursor-row-binding]], [[confirm-yes-no-dialog]]
