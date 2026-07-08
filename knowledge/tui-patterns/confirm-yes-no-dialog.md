# Pattern D — Confirm / Yes-No Dialog

Recognize a yes/no prompt in the last 1-3 lines (question + bracket/paren choice), infer the default from capitalization, and answer with `y\r` / `n\r` / bare Enter — retrying with the full word if it persists.

### Recognition
High confidence — question + choice tokens: `[y/N]`, `[Y/n]`, `(y/n)`, `(yes/no)`, `[yes/no]`, `[Y/n]?`, `[y/N]?`, plus verbs `Proceed?`, `Continue?`, `Are you sure?`, `Do you want to continue?`, `Overwrite?`, `Remove?`.
Examples: apt `Do you want to continue? [Y/n]`; ssh `Are you sure you want to continue connecting (yes/no/[fingerprint])?`; installer `Proceed ([Y]es/[N]o)?`.

### Default-choice detection (capitalization convention)
- `[Y/n]`, `(Y/n)`, `[YES/no]` → **default YES** → bare Enter accepts.
- `[y/N]`, `(y/N)`, `[yes/NO]` → **default NO** → bare Enter rejects.
- `[Y]es/[N]o` alone may only show hotkeys, no default. `(yes/no)` has no default unless one is capitalized or text says so. `Ok to proceed? (y)` usually accepts only `y`.

### Drive
```
if prompt has "(yes/no" or "type yes" or ssh host-key form: accept = "yes\r"
elif explicit default exists and desired == default:            send "\r"
elif desired == yes:                                            "y\r"
else:                                                           "n\r"
```
Accept `y\r` (0x79 0x0d); full `yes\r` when prompt says `(yes/no)`/"type yes". Reject `n\r`/`no\r`. Abort Ctrl-C `\x03`.

### Done
Prompt line disappears / new output follows / process exits / shell prompt returns. If the SAME prompt remains after 300-500 ms the answer was not accepted: retry once with `yes\r` (if yes/no form), or re-parse (maybe no default existed and bare Enter was ignored).

**Source:** apt-get(8) https://manpages.ubuntu.com/manpages/focal/man8/apt-get.8.html ; ssh host-key prompt (form quoted from ssh)

**See also:** [[done-signal-layering]], [[key-encoding-reference]], [[wizard-installer-flow]], [[cursor-row-binding]]
