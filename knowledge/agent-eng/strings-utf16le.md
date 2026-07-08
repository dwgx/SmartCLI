# strings -e l for Windows binaries

**Statement:** Default `strings` misses Windows wide-char UI text; use `-e l` to catch UTF-16LE strings.

**Detail / real params:**
- `-n <min>` — minimum string length (default 4).
- `-e l` — 16-bit little-endian encoding, i.e. **UTF-16LE**, which is how Windows stores wide-char UI strings.
- `-a` — scan the whole file (all sections), not just loadable/initialized data.

Default mode is 7-bit and MISSES Windows wide-char UI strings, so `-e l` is required when mining a Windows binary for layout / label constants.

**Source:** https://sourceware.org/binutils/docs/binutils/strings.html

**See also:** [[ripgrep-binary-search]], [[hunt-the-esc-byte]], [[node-sea-blob]], [[source-maps]]
