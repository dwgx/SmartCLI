# node-pty on Windows = ConPTY only

**Statement:** Modern node-pty uses ConPTY exclusively on Windows; winpty support was removed.

**Detail / real params:** winpty backend support has been removed from node-pty. It now requires ConPTY, available on Windows 10 build 1809 and later. This dictates the minimum supported OS and is why older winpty-based tips are stale.

**Source:** https://github.com/microsoft/node-pty

**See also:** [[node-pty]], [[pywinpty]], [[pexpect-no-windows-pty]]
