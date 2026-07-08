# Node SEA blob extraction

**Statement:** A Node single-executable app embeds its bundled JS in a named region marked by a sentinel fuse.

**Detail / real params:**
- Region name: `NODE_SEA_BLOB` — stored as a PE resource (Windows), an ELF note (Linux), or a Mach-O section (macOS).
- Sentinel fuse: `NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2`, flipped to `1` when a blob has been injected.

Locate that region / fuse to carve the embedded JS out of a single-file Node application.

**Source:** https://nodejs.org/api/single-executable-applications.html

**See also:** [[ripgrep-binary-search]], [[strings-utf16le]], [[source-maps]], [[hunt-the-esc-byte]]
