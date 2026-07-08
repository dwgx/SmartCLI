# pywinpty dual backend

**Statement:** pywinpty is the Windows equivalent of pexpect, supporting both native ConPTY and a winpty fallback.

**Detail / real params:** High-level API mirrors pexpect: `PtyProcess.spawn`, `write`, `readline`, `isalive`. Low-level API: `PTY(cols, rows)` with `set_size(cols, rows)`. Supports both ConPTY (native) and winpty (fallback) backends. This is the driver of choice for SmartCLI on Windows.

**Source:** https://github.com/andfoy/pywinpty

**See also:** [[pexpect-no-windows-pty]], [[node-pty-windows-conpty]], [[pty-vs-pipe]], [[pexpect-encoding]]
