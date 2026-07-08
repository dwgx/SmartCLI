# Alternate Screen Buffer Detection

The strongest signal that a full-screen TUI launched is that it entered the alternate screen buffer; detect the switch sequences in the raw byte stream.

| Seq | Bytes | Meaning |
|---|---|---|
| ESC[?1049h | `\x1b[?1049h` | save cursor + switch to alt screen + clear (modern smcup) |
| ESC[?1049l | `\x1b[?1049l` | restore normal screen (rmcup) |
| ESC[?1047h/l | `\x1b[?1047h` / `l` | alt screen buffer on/off |
| ESC[?47h/l | `\x1b[?47h` / `l` | older alt screen on/off |
| ESC[2J | `\x1b[2J` | clear screen |
| ESC[H | `\x1b[H` | cursor home |
| ESC[?25l / ?25h | `\x1b[?25l` / `h` | hide / show cursor |
| ESC[?1h / ?1l | `\x1b[?1h` / `l` | DECCKM application / normal cursor keys |
| ESC[?1000h,1002h,1003h,1006h | mouse tracking modes | TUI wants mouse |
| ESC[?2004h | bracketed paste | weak signal alone |

Mode heuristic:
```
if saw_alt_enter and not saw_alt_leave: mode = fullscreen_tui
elif many cursor-address + clears + cursor-hide: mode = screen-oriented
elif mostly printable + CR/LF + prompt regex: mode = line-oriented
else: mode = unknown/mixed
```
Use a real parser, not only regex: CSI can arrive as 8-bit `0x9b`, and escapes split across reads.

**Source:** https://invisible-island.net/xterm/ctlseqs/ctlseqs.html

**See also:** [[screen-snapshot-capture]], [[application-cursor-mode]], [[tmux-capture-pane]], [[quiescence-detection]], [[alternate-screen-buffer]] (why naive capture reads stale content), [[tmux-alternate-screen]] (VT + per-pane semantics)
