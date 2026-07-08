# Pattern F — Form / Field Input (dialog, whiptail, debconf)

Recognize a boxed form by frame + buttons + label/value rows, and drive it as a state machine: locate the focused field, fill, Tab to target, Space for checkbox/radio, Tab to OK, Enter.

### Recognition
Strong signals:
- Box-drawn/ASCII frame with buttons `<Ok>`, `<Cancel>`, `[ OK ]`, `[Cancel]`.
- Multiple label+editable-value rows aligned in columns (`Name: ____`, `Version: 1.0.0`).
- Cursor inside/after an input field, NOT at a shell prompt.
- Focused field has reverse-video/highlight/colored bg, or the cursor lands within its bounds.
- Underline runs / blank boxed regions / fixed-width value cells.
- Bottom buttons reachable by Tab: OK / Cancel / Help / Back / Next.

Detectors (regex on de-ANSI'd text, keep cursor/attrs):
```
buttons     (?i)(<\s*ok\s*>|<\s*cancel\s*>|\[\s*ok\s*\]|\[\s*cancel\s*\])
field_label ^\s*[A-Za-z][A-Za-z0-9 _./-]{1,30}\s*[:=]\s*\S?.*$
checkbox    \[[ xX]\]|\([ xX]\)
radio       \([* ]\)|<[* ]>
```
Require ≥1 of: 2+ field_label rows + buttons; cursor inside underlined/boxed region; reverse-video field + nearby label.

### Drive
- Fill focused field: safest generic = Backspace `\x7f` × N to clear default, then type text. (Ctrl-U `\x15` clears line only in readline-style widgets, not universal.)
- Next field: Tab `\t`, Down `\x1b[B`, or dialog Ctrl-N `\x0e`. Prev: Shift-Tab `\x1b[Z`, Up `\x1b[A`, or Ctrl-P `\x10`.
- Within field: Left `\x1b[D` Right `\x1b[C` Home `\x1b[H` End `\x1b[F` Backspace `\x7f`.
- Toggle checkbox/radio: Space `\x20`. Submit: Enter `\r`. In a multiline edit box, Tab to OK first, then Enter.

State machine: identify focused field (cursor/highlight) → fill → Tab/Shift-Tab to target → Space for checkbox/radio → Tab to OK/Next → Enter → wait until frame gone / screen changes.

### Done
Frame disappears and prior output resumes / next wizard page replaces it / process exits / new prompt appears / no OK/Cancel/field remains. Stuck: same field focused after Enter; validation text `(?i)(required|invalid|must|cannot|error|try again)`; screen hash unchanged after submit (ignoring cursor blink).

**Source:** dialog(1) https://linux.die.net/man/1/dialog ; whiptail https://www.mankier.com/1/whiptail ; debconf https://manpages.debian.org/bullseye/debconf-doc/debconf.7.en.html

**See also:** [[wizard-installer-flow]], [[key-encoding-reference]], [[verify-movement-step-by-step]], [[snapshot-stability-hash]], [[cursor-row-binding]]
