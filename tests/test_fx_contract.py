"""Frame-contract test for the cmd-art fx framework (deterministic, no TTY).

Every :class:`fx.base.Effect` is a PURE frame producer: ``render(ctx) -> str``
must return a frame of EXACTLY ``ctx.height`` rows, and no row may be wider than
``ctx.width`` display cells (a row wider than the frame is the "overflows at N
cols" defect the terminal would wrap; a frame with the wrong row count is
under/overfill). "Field"-style effects (fire, plasma, donut, ...) fill EVERY
cell, so for those the width must equal ``ctx.width`` exactly.

The live harness (verify_fx.py) proves effects RUN and keep the alt-screen /
truecolor invariants, and probe.py checks row count + an *upper* width bound.
Neither asserts the EXACT per-line cell width for the solid-fill effects, nor
sweeps degenerate ctx sizes (tiny 1x1/2x2). This test closes that gap by
rendering each effect at several sizes / frames and asserting the contract with
the repo's AUTHORITATIVE display-width function (ui.core.width -- wcwidth-backed,
ANSI-stripping, CJK/emoji aware -- the same measure the engine and pyte use).

Contracts asserted (HARD -> non-zero exit):
  C1 row count == ctx.height           for ALL effects at ALL sizes.
  C2 no row wider than ctx.width        for ALL effects at REALISTIC sizes.
  C3 every row width == ctx.width       for SOLID (full-fill) effects, at
                                        realistic + narrow + tiny sizes.
  C4 render() never raises              for ALL effects at tiny (1x1/2x2) sizes.
  C5 no UNEXPECTED narrow overflow      at (20,8): only the documented
                                        allowlist below may exceed width.

SOFT (reported, never fails a correct shipped build):
  * known narrow-width overflow of the sparse text effects (see allowlist),
  * width defects at the degenerate tiny sizes (1x1/2x2), which some effects
    legitimately cannot honour (e.g. image2ascii's 2-cell half-block glyph).

Usage: python tests/test_fx_contract.py [name ...]   (default: everything)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skills" / "cmd-art"))
sys.path.insert(0, str(ROOT / "skills" / "tui-ui"))

import fx.registry as registry  # noqa: E402
from fx.base import FrameCtx  # noqa: E402
from fx.theme import get_theme  # noqa: E402

# ---- authoritative display-cell width (same fn the engine + pyte agree on) ---
# Reuse ui.core.width: strips ANSI/SGR then sums per-codepoint wcwidth (wide
# glyphs = 2, combining/ZWJ = 0). Falling back to a matching local stripper only
# if the tui-ui skill is somehow unavailable keeps this test self-contained.
try:
    from ui.core import width as visible_width  # type: ignore
except Exception:  # pragma: no cover - tui-ui should always be importable
    import re
    import unicodedata

    _ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

    def visible_width(s: str) -> int:  # type: ignore
        s = _ANSI_RE.sub("", s)
        w = 0
        for ch in s:
            o = ord(ch)
            if o == 0 or unicodedata.combining(ch) or o in (0x200D, 0xFE0E, 0xFE0F):
                continue
            if o < 32 or 0x7F <= o < 0xA0:
                continue
            w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        return w


# --------------------------------------------------------------------------
# Test matrix
# --------------------------------------------------------------------------
# Realistic frame sizes: the contract is HARD here.
REALISTIC = [(80, 24), (120, 40), (40, 12)]
# Narrow but real terminal: HARD row-count + curated overflow allowlist (C5).
NARROW = [(20, 8)]
# Degenerate/tiny: HARD row-count + no-crash; width is SOFT (reported only).
TINY = [(2, 2), (1, 1)]

# Effects whose rows are known to exceed ctx.width at the (20,8) narrow size,
# because they emit text without clipping to ctx.width. This is a genuine
# frame-contract weakness in the shipped effect (documented as a FINDING in the
# report), NOT a test-measurement artifact -- the raw text really is wider than
# the frame. Listed here so the test still PASSES on today's shipped build while
# a hard gate guards against any *new* effect regressing the same way.
KNOWN_NARROW_OVERFLOW = {"decrypt", "typewriter"}

results: list[tuple[str, bool, str]] = []
findings: list[str] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def frames_for(cls) -> list[tuple[float, int]]:
    """(t, frame_index) samples to render. Animated effects get a few frames to
    catch frame-dependent raggedness; static effects only ever draw one frame."""
    if cls.is_animated(cls.param_defaults()):
        return [(0.0, 0), (0.7, 5), (3.1, 93)]
    return [(0.7, 0)]


def render(cls, w: int, h: int, t: float, fi: int) -> str:
    """Build the ctx the CLI would and render ONE frame (mirrors probe.py /
    fx.core.render_once: fresh instance, setup(), render(), teardown())."""
    eff = cls()
    eff.setup()
    try:
        ctx = FrameCtx(t=t, frame_index=fi, width=w, height=h,
                       theme=get_theme(cls.preferred_theme),
                       params=cls.param_defaults())
        return eff.render(ctx)
    finally:
        try:
            eff.teardown()
        except Exception:
            pass


def _rows(frame: str) -> list[str]:
    """Split a frame into its rows -- the AUTHORITATIVE row measure, identical to
    probe.py's ``frame.split("\\n")``. The contract is "ctx.height rows joined by
    newlines, NO trailing newline" (see fx.base), so a plain split yields exactly
    ctx.height rows. We deliberately do NOT strip a trailing newline: sparse
    effects pad with empty rows, so a frame can legitimately END in "\\n" where
    that newline is the separator before a final empty row -- stripping it would
    drop a real row and under-count the frame."""
    return frame.split("\n")


def _is_solid(cls) -> bool:
    """A SOLID (full-fill) effect writes every cell, so every row is EXACTLY
    ctx.width. Classified empirically at the canonical 80x24 across its frames:
    if no row deviates from 80, it is a field/particle effect and must honour
    the exact-width contract everywhere. Sparse text/banner/image effects (which
    legitimately leave blank cells) are excluded from the exact-width gate."""
    for (t, fi) in frames_for(cls):
        for ln in _rows(render(cls, 80, 24, t, fi)):
            if visible_width(ln) != 80:
                return False
    return True


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
def check_rowcount(cls) -> None:
    """C1: every rendered frame has EXACTLY ctx.height rows, at ALL sizes."""
    for (w, h) in REALISTIC + NARROW + TINY:
        for (t, fi) in frames_for(cls):
            rows = _rows(render(cls, w, h, t, fi))
            if len(rows) != h:
                record(f"rowcount {cls.name}", False,
                        f"{w}x{h} t={t}: {len(rows)} rows != {h}")
                return
    record(f"rowcount {cls.name}", True, "exact rows at every size")


def check_no_overflow(cls) -> None:
    """C2: no row wider than ctx.width at REALISTIC sizes (all effects)."""
    for (w, h) in REALISTIC:
        for (t, fi) in frames_for(cls):
            for i, ln in enumerate(_rows(render(cls, w, h, t, fi))):
                cw = visible_width(ln)
                if cw > w:
                    record(f"no-overflow {cls.name}", False,
                            f"{w}x{h} t={t} row {i}: width {cw} > {w}")
                    return
    record(f"no-overflow {cls.name}", True, "no row exceeds width")


def check_exact_width(cls) -> None:
    """C3: SOLID effects fill every cell -> width == ctx.width, at realistic +
    narrow + tiny sizes. Sparse effects are skipped (SOFT-reported elsewhere)."""
    if not _is_solid(cls):
        record(f"exact-width {cls.name}", True, "sparse effect (exact-width n/a)")
        return
    for (w, h) in REALISTIC + NARROW + TINY:
        for (t, fi) in frames_for(cls):
            for i, ln in enumerate(_rows(render(cls, w, h, t, fi))):
                cw = visible_width(ln)
                if cw != w:
                    record(f"exact-width {cls.name}", False,
                            f"{w}x{h} t={t} row {i}: width {cw} != {w}")
                    return
    record(f"exact-width {cls.name}", True, "every row == width (solid fill)")


def check_narrow_allowlist(cls) -> None:
    """C5: at the narrow (20,8) size, overflow is a HARD failure UNLESS the
    effect is on the documented KNOWN_NARROW_OVERFLOW allowlist. This is the
    regression gate that would catch a NEW effect emitting unclipped rows."""
    for (w, h) in NARROW:
        for (t, fi) in frames_for(cls):
            for i, ln in enumerate(_rows(render(cls, w, h, t, fi))):
                cw = visible_width(ln)
                if cw > w:
                    if cls.name in KNOWN_NARROW_OVERFLOW:
                        findings.append(
                            f"narrow overflow (known) {cls.name} {w}x{h} "
                            f"t={t} row {i}: width {cw} > {w}")
                        record(f"narrow {cls.name}", True,
                                f"known overflow tolerated (row {i} width {cw}>{w})")
                        return
                    record(f"narrow {cls.name}", False,
                            f"UNEXPECTED overflow {w}x{h} t={t} row {i}: "
                            f"width {cw} > {w} (not in allowlist)")
                    return
    if cls.name in KNOWN_NARROW_OVERFLOW:
        # allowlisted but no longer overflowing -> the effect was fixed; the
        # allowlist is now stale (report so it can be tightened).
        findings.append(f"allowlist stale: {cls.name} no longer overflows at 20x8")
    record(f"narrow {cls.name}", True, "fits 20x8 (or known)")


def check_tiny_no_crash(cls) -> None:
    """C4: render() must not raise at degenerate 1x1 / 2x2 sizes. Width defects
    at these sizes are SOFT (some effects legitimately can't honour 1x1)."""
    for (w, h) in TINY:
        for (t, fi) in frames_for(cls):
            try:
                rows = _rows(render(cls, w, h, t, fi))
            except Exception as exc:  # a crash IS a hard failure (finding)
                record(f"tiny-safe {cls.name}", False,
                        f"raised at {w}x{h} t={t}: {exc!r}")
                return
            for i, ln in enumerate(rows):
                cw = visible_width(ln)
                if cw != w:
                    findings.append(
                        f"tiny width (soft) {cls.name} {w}x{h} row {i}: "
                        f"width {cw} != {w}")
    record(f"tiny-safe {cls.name}", True, "no crash at 1x1/2x2")


def main(argv: list[str]) -> int:
    registry.load_all()
    only = set(argv)
    effects = [c for c in registry.all_effects() if not only or c.name in only]
    sizes = REALISTIC + NARROW + TINY
    for cls in effects:
        check_rowcount(cls)
        check_no_overflow(cls)
        check_exact_width(cls)
        check_narrow_allowlist(cls)
        check_tiny_no_crash(cls)

    failed = [r for r in results if not r[1]]
    if findings:
        print("\nFINDINGS (soft / documented):")
        for f in findings:
            print("  - " + f)
    checks_per = 5
    print(f"\n{len(effects)} effects x {len(sizes)} sizes "
          f"({checks_per} contracts each)")
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

