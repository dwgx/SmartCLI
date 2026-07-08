# CRLF translation is termios

**Statement:** CR/LF newline translation on a PTY is controlled by termios output/input flags, not by the program.

**Detail / real config flags:**
- `OPOST` — master switch enabling output post-processing.
- `ONLCR` — "Map NL to CR-NL on output" (why PTY output has `\r\n` where the program wrote `\n`).
- `ICRNL` — "Map CR to NL on input" (why pressing Enter / sending `\r` arrives as `\n`).

To normalize captured PTY output to raw LF, account for `ONLCR`; to send Enter correctly, remember `ICRNL` maps `\r`→`\n` on input.

**Source:** https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/termios.h.html

**See also:** [[pty-vs-pipe]], [[node-pty]], [[isatty-branching]]
