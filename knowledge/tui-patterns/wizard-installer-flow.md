# Pattern H — Wizard / Multi-Step Installer Flow

Recognize a step-at-a-time flow (npm init, create-vite, debconf/dialog pages) that advances after each Enter, classify each step into one of four kinds, drive it, and confirm the screen materially changed before moving on.

### Recognition
- One current question/prompt at a time; screen advances after each Enter.
- Step markers: `Step 1 of 4`, `1/4`, `(1 of 4)`.
- Modern JS-CLI glyphs: `? Project name: › vite-project`, `◇ Select a framework:`, `◆ ...`, `› React`.
- npm init sequence: `package name:`, `version:`, `description:`, `entry point:`, `test command:`, `git repository:`, `keywords:`, `author:`, `license:`.
- debconf/dialog pages: framed box `Package configuration` + buttons `<Ok> <Yes> <No> <Cancel> <Back> <Next>`; menu page = vertical choices with one highlighted; yes/no page = question + Yes/No buttons.

Regexes:
```
step_counter     (?i)\b(step\s*)?\d+\s*(of|/)\s*\d+\b
npm_init         ^\s*(package name|version|description|entry point|test command|git repository|keywords|author|license):(?:\s*\([^)]*\))?\s*$
text_prompt      ^\s*[?◇◆]\s+.+:\s*(?:›\s*)?.*$
dialog_buttons   (?i)(<\s*yes\s*>|<\s*no\s*>|<\s*ok\s*>|<\s*next\s*>|<\s*back\s*>)
completion       (?i)\b(done|success|completed|installed|created|scaffolding project|happy hacking|now run|wrote to)\b
validation_error (?i)\b(required|invalid|already exists|not empty|must|please choose|try again|error)\b
```
Classify: text-prompt (cursor after `:`/`› default`, no dominant list); menu-select (choices, one highlighted or prefixed `> ❯ › * (*)`, prompt says Select/Choose/Which); yes/no (question + `(y/N)`/`(Y/n)`/`[y/N]`/yes/no); dialog page (framed + OK/Cancel/Next/Back/Yes/No).

### Drive
- Text prompt: type answer + `\r`; default `\r`; clear default Backspace × N (or Ctrl-U in inquirer/readline) then answer + `\r`.
- Menu select: Down `\x1b[B`/Up `\x1b[A` to target, then `\r`; sometimes Space `\x20` toggles first.
- Yes/no: `y\r`/`n\r`, or Left/Right `\x1b[D`/`\x1b[C` between buttons then Enter.
- dialog/whiptail menu: Up/Down to item, Space for checklist/radio, Tab `\t` to OK, Enter.

Examples: npm init — answer each field or Enter for defaults; final `Is this OK? (yes)` → `\r` or `yes\r`, done at `Wrote to ... package.json`. create-vite — `? Project name: ›` → `my-app\r`; `Select a framework`/`variant` → arrows + `\r`; done at `Done. Now run:` / `Scaffolding project in ...`. git rebase -i is NOT a wizard screen — it opens $EDITOR with a todo buffer (`^pick [0-9a-f]{7,40} .+`, `# Commands:`); drive via editor (vim `:wq\r`, nano Ctrl-O `\x0f` Enter Ctrl-X `\x18`); done at `Successfully rebased and updated ...`.

### Advance detection (per step)
1. Hash normalized screen BEFORE sending. 2. Send answer + submit. 3. Poll until: hash changes materially / question regex changes / step counter increments / prompt disappears / completion regex appears. 4. Same question + validation_error → stuck/invalid. 5. Same question, no error, after timeout → retry submit once, then surface ambiguous state.

### Done
Completion regex appears, OR app exits + shell prompt returns, OR final install output stable + prompt returns, AND no wizard/dialog/menu/question remains. NOT done while: current prompt active, focus on OK/Next after validation msg, spinner/gauge updating, apt/dpkg still `Setting up`/`Unpacking`/`Processing triggers`.

**Source:** Vite https://vite.dev/guide/ ; CRA https://create-react-app.dev/docs/getting-started/ ; npm package.json https://docs.npmjs.com/files/package.json/ ; git rebase https://git-scm.com/docs/git-rebase ; debconf/dialog/whiptail (see [[form-field-input]])

**See also:** [[form-field-input]], [[confirm-yes-no-dialog]], [[list-menu-navigation]], [[verify-movement-step-by-step]], [[snapshot-stability-hash]], [[progress-spinner-waiting]]
