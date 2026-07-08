# tmux send-keys -l (literal)

**Statement:** `send-keys -l` sends a literal UTF-8 string, bypassing key-name lookup.

**Detail / real params:** Without `-l`, strings that happen to match key names (e.g. `Enter`, `C-m`) get reinterpreted as those keys. `-l` disables that lookup so the text is sent verbatim. Named keys like `C-m` / `Enter` are sent by name (without `-l`). `-H` sends keys as hexadecimal byte values.

**Source:** https://man.openbsd.org/tmux

**See also:** [[tmux-capture-pane]], [[tmux-control-mode]], [[application-cursor-keys-deckm]]
