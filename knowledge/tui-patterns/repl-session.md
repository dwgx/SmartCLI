# Pattern G — REPL Session

Recognize a REPL by matching a primary-prompt regex on the CURSOR ROW, send `command + \r`, and treat the command as done when the primary prompt reappears on the cursor row — handling continuation prompts as "wants more input".

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
READY when: cursor is on the same row as a primary prompt (right after prompt text or after echoed input following it); prompt is the last non-empty visible line; screen stable ≥1 poll. Do NOT treat output lines as prompts unless the cursor is on/after that line — cursor-row binding is mandatory (see [[cursor-row-binding]]).

### Drive
- Send command: `bytes(command) + \r`. Wait for primary prompt to reappear on cursor row = done.
- Exit: Ctrl-D (EOF) `\x04`; Node `.exit\r`; Python `exit()\r`/`quit()\r`; GDB/LLDB `quit\r`.
- Multi-line continuation: if cursor row matches a continuation prompt, send the next line + `\r`, don't wait for output yet. Python block:
```
"for i in range(3):\r"  -> wait /^... $/
"    print(i)\r"        -> wait /^... $/
"\r"                    -> wait /^>>> $/   (blank line ends block)
```
Node function: `function f() {\r` → `... `, `return 1\r` → `... `, `}\r` → `> `.

### Done
Primary prompt regex reappears on cursor row after echo/output AND stable 1 poll AND not at a continuation prompt. NOT done when: cursor row = secondary prompt, output still appending, or debugger inferior running with no `(gdb)`/`(lldb)` visible. GDB pager `--Type <RET> for more, q to quit, c to continue--` → send Space or `c`, keep waiting for `(gdb) `. Allow the caller to override prompt regexes (GDB `set prompt`).

**Source:** Python sys.ps1/ps2 https://docs.python.org/3/library/sys.html ; Node REPL https://nodejs.org/learn/command-line/how-to-use-the-nodejs-repl ; GDB https://ftp.gnu.org/old-gnu/Manuals/gdb/html_chapter/gdb_17.html ; IPython https://ipython.readthedocs.io/en/stable/config/details.html ; IRB https://ruby-doc.org/3.4.1/stdlibs/irb/IRB.html ; LLDB https://lldb.llvm.org/use/tutorial.html

**See also:** [[cursor-row-binding]], [[key-encoding-reference]], [[done-signal-layering]], [[quiescence-detection]]
