# pexpect has no PTY on Windows

**Statement:** pexpect's PTY-based spawning is POSIX-only; Windows gets a limited non-PTY fallback.

**Detail / real params:** `spawn` and `run()` are POSIX-only. On Windows, pexpect offers `PopenSpawn`, which has no pty and is explicitly documented as "not a direct replacement." For real PTY behavior on Windows, use pywinpty / node-pty / ConPTY instead.

**Source:** https://pexpect.readthedocs.io/en/stable/overview.html

**See also:** [[pywinpty]], [[node-pty]], [[node-pty-windows-conpty]], [[pty-vs-pipe]]
