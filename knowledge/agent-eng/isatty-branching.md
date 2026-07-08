# isatty branching

**Statement:** Programs change their output behavior depending on whether stdout is a tty.

**Detail / real params:** When stdout is not a tty, programs typically switch to full buffering and disable color. pexpect's echo control is unsupported when `isatty()` returns False. This is the core motivation for driving CLIs through a PTY rather than a pipe.

**Source:** https://pexpect.readthedocs.io/en/stable/api/pexpect.html

**See also:** [[pty-vs-pipe]], [[crlf-termios]], [[pexpect-encoding]]
