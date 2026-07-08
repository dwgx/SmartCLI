# Source maps recover original source

**Statement:** A shipped source map lets you recover the real original source, not just prettified minified code.

**Detail / real params:**
- Marker comment: `//# sourceMappingURL=`.
- The map is JSON; `sourcesContent` holds the inlined original source text.
- `mappings` is a Base64 VLQ-encoded field mapping generated positions back to originals.

If a `.map` ships alongside a bundle, you get the actual source.

**Source:** spec https://tc39.es/ecma426/ ; consumer library https://www.npmjs.com/package/source-map ; VLQ codec https://github.com/jridgewell/sourcemap-codec

**See also:** [[node-sea-blob]], [[strings-utf16le]], [[ripgrep-binary-search]]
