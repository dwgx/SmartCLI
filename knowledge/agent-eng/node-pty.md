# node-pty API

**Statement:** node-pty is the canonical Node.js driver for spawning processes under a real PTY.

**Detail / real params:**
```js
const pty = require('node-pty');
const p = pty.spawn(file, args, { name, cols, rows, cwd, env });
p.onData(data => { /* stream terminal output */ });
p.write('ls\r');            // note: carriage return, not \n
p.resize(cols, rows);
```
Key surface: `spawn(file, args, opts)`, `onData`, `write`, `resize(cols, rows)`.

**Source:** https://github.com/microsoft/node-pty

**See also:** [[node-pty-windows-conpty]], [[pywinpty]], [[pty-vs-pipe]]
