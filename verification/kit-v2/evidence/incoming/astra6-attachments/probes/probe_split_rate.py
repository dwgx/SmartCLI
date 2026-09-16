"""How often does the SGR-split defect actually bite? Chunk-size sweep over a
realistic mixed CJK + truecolor stream. Pure in-memory, read-only w.r.t. the repo.

Run: python probe_split_rate.py <repo-root>
"""
from __future__ import annotations

import random
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else r"D:\Project\SmartCLI"
sys.path.insert(0, REPO)

from smartcli_core.screen_model import ScreenModel  # noqa: E402

# A stream shaped like modern CLI output: every line carries a truecolor or
# sub-parameter SGR, which is exactly the Neovim/kitty/delta/delta-style output
# the colon normaliser exists for.
STREAM = "".join(
    f"\x1b[38:2::{i * 7 % 256}:0:0m行{i} 中文内容\x1b[0m \x1b[4:3m下划线\x1b[0m ok\n"
    for i in range(200)
).encode("utf-8")

ref = ScreenModel(cols=80, rows=24)
ref.feed(STREAM)
ref_text = ref.screen.display
ref_dirty = ref.feed_errors

print(f"stream={len(STREAM)} bytes, escapes with ':' = {STREAM.count(b':')}")

for chunk in (1, 2, 4, 8, 16, 64, 256, 1024, 4096, 65536):
    bad = 0
    trials = 40
    for seed in range(trials):
        rng = random.Random(seed)
        m = ScreenModel(cols=80, rows=24)
        i = 0
        while i < len(STREAM):
            n = rng.randint(1, chunk)
            m.feed(STREAM[i:i + n])
            i += n
        if m.screen.display != ref_text:
            bad += 1
    pct = 100.0 * bad / trials
    print(f"  chunk<= {chunk:>6} bytes : {bad:>2}/{trials} streams corrupted ({pct:4.0f}%)")

print(f"\nreference feed_errors={ref_dirty} (pyte itself tolerates the debris; nothing counts it)")
