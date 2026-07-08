# Use a real PTY, not a pipe

**Statement:** Spawn the child process under a pseudoterminal so it behaves as if attached to a real terminal.

**Detail / real params:** Non-tty stdout is fully block-buffered and most tools suppress color when `isatty()` is False. pexpect gates its echo-control features on the child being a real tty; drive interactive programs through a PTY rather than `subprocess` pipes.

**Source:** https://pexpect.readthedocs.io/en/stable/api/pexpect.html

**See also:** [[isatty-branching]], [[pexpect-encoding]], [[pywinpty]], [[node-pty]]
