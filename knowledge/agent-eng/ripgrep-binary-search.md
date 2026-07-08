# ripgrep binary search

**Statement:** ripgrep stops at the first NUL by default; flags let it search packed exes/blobs without truncation.

**Detail / real params:**
- `-a` / `--text` — disable binary detection, treat the file as text.
- `--binary` — search binary files but don't dump the raw matching bytes.
- `-o` — only-matching (print just the matched substring).
- `-U` — multiline matching.
- `--no-mmap` — read via normal I/O for consistent binary detection.

Use these to grep single-file node apps, packed exes, and blobs for embedded constants.

**Source:** https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md

**See also:** [[strings-utf16le]], [[hunt-the-esc-byte]], [[node-sea-blob]]
