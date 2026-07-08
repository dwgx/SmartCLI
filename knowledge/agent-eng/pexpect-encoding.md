# pexpect encoding is bytes by default

**Statement:** pexpect operates in bytes mode unless you explicitly request str mode.

**Detail / real params:** Pass `encoding='utf-8'` to get str mode. Set `codec_errors='replace'` or `codec_errors='ignore'` to survive non-UTF8 / garbage bytes without a decode crash. The old `spawnu` class is legacy (deprecated since pexpect 4.0) — use `spawn(..., encoding='utf-8')` instead.

**Source:** https://pexpect.readthedocs.io/en/stable/api/pexpect.html

**See also:** [[pty-vs-pipe]], [[pexpect-no-windows-pty]], [[crlf-termios]]
