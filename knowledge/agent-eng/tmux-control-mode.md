# tmux control mode (-CC)

**Statement:** tmux control mode exposes a machine-parseable protocol for programmatic driving.

**Detail / real params:** `-C` starts control mode; `-CC` starts control mode and additionally disables echo. Use control mode when a program (rather than a human) is driving tmux and needs structured, parseable output.

**Source:** https://man.openbsd.org/tmux

**See also:** [[tmux-send-keys-literal]], [[tmux-capture-pane]]
