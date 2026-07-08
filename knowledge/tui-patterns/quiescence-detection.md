# Quiescence Detection ("output settled")

No universal "waiting for input" bit exists; layer timing + snapshot-stability heuristics to decide when output has settled.

Condition:
```
quiescent when:
  no PTY bytes for idle_ms
  AND visible snapshot hash unchanged for stable_ms
  AND no pending partial escape sequence
  AND (optional) recognizer says cursor is at a prompt/input area
```

Thresholds (idle_ms / stable_ms):
| Situation | idle | stable | note |
|---|---|---|---|
| Fast local shell cmd | 50-100 | 50-100 | |
| TUI redraw after keypress | 75-150 | 100-200 | avoid capturing mid-frame |
| Slow/network CLI | 250-500 | 250-500 | |
| Animated/progress UI | 500-1000 | require semantic condition | snapshot may never stabilize |
| Remote SSH/high latency | 500-2000 | 500-2000 | tune by RTT |

Read loop:
```python
last_byte = last_change = now()
while True:
    data = read_pty(timeout=read_poll_ms)
    if data:
        last_byte = now(); emu.feed(data)
        if snapshot_hash() != last_hash:
            last_change = now(); last_hash = snapshot_hash()
    if now()-last_byte >= idle_ms and now()-last_change >= stable_ms:
        break
```

**Source:** primary/synthesized — thresholds are engineering guidance distilled in the project TUI-patterns research digest (`research/R4-tui-patterns.md`), cross-checked against the xterm ctlseqs and fzf man page. No single external authority publishes these numbers; they are tuning defaults.

**See also:** [[snapshot-stability-hash]], [[screen-snapshot-capture]], [[done-signal-layering]], [[progress-spinner-waiting]]
