# Truecolor Passthrough in tmux

**Statement:** tmux only forwards 24-bit color when the OUTER terminal is advertised as RGB-capable; otherwise it silently quantizes app RGB to the 256/16-color palette — a config problem, not an app bug.

**Exact config:**
```tmux
# modern (tmux >= 3.2): terminal-features describes the OUTER terminal
set -g default-terminal "tmux-256color"
set -as terminal-features ",*:RGB"          # or real patterns: ",alacritty*:RGB" ",xterm-kitty:RGB" ",wezterm:RGB" ",foot*:RGB"

# older-compatible (any version): Tc is tmux's pre-3.2 equivalent of terminfo RGB
set -as terminal-overrides ",*:Tc"
```
- `RGB` = official terminfo capability flag; `Tc` = tmux private equivalent.
- Detection flow (tty-term.c): terminfo -> terminal-features -> COLORTERM -> terminal-overrides. `COLORTERM=truecolor`/`24bit` is a hint tmux also treats as RGB evidence, but is NOT a substitute for an emulator that renders RGB.
- `$TERM` INSIDE tmux is `tmux-256color`/`screen*`, NOT the outer terminal's TERM.
- Degradation: if app writes RGB but outer terminal not marked RGB, tmux maps RGB -> nearest 6x6x6 cube / grayscale entry (colour_find_rgb), then to 16 if <256. The wire bytes are never wrong; tmux flattens them.

Verify:
```sh
tmux display -p '#{client_termname} #{client_termfeatures}'   # look for RGB
tmux info | grep -E 'RGB|Tc|setrgb|colors'
printf '\033[48;2;255;0;0m  \033[48;2;0;255;0m  \033[48;2;0;0;255m  \033[0m\n'  # 3 distinct blocks = working
```

**Source:** https://github.com/tmux/tmux/wiki/FAQ#how-do-i-use-rgb-colour (also man https://man7.org/linux/man-pages/man1/tmux.1.html ; degrade issue https://github.com/tmux/tmux/issues/299 ; tty-term.c/colour.c — project research R6 §1, R5 §B.6)

**See also:** [[ansi-sgr-color]], [[tmux-alternate-screen]], [[tmux-capture-pane]], [[resize-sigwinch-handling]], [[box-drawing-glyphs]]
