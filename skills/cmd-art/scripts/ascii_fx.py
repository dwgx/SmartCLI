#!/usr/bin/env python3
"""ascii_fx.py -- legacy cmd-art entry point, now a thin shim over the fx framework.

The real engine lives in ``skills/cmd-art/fx/`` (registry + themes + play loop).
This script preserves the ORIGINAL surface so old commands and imports keep
working:

* CLI:   ``python ascii_fx.py [--fps N] [--seconds N] [--once] [--width W]
  [--height H] <sphere|plasma|wave|rain|text3d> [effect args]``
* Imports: ``from ascii_fx import sphere_frame, plasma_frame, hgrad, big_text,
  block_text, FONT, Rain, run, render_once, rgb, RESET, enable_vt, term_size``

Behavior notes vs. the original:
* No --seconds/--once still runs until Ctrl-C (translated to ``--forever``).
* ``text3d --seconds N`` without ``--shimmer`` renders one static frame (the
  old script looped an identical frame; looping a static image was pointless).

New work should target the fx CLI directly:
``python skills/cmd-art/fx/cli.py play <effect> ...`` (see fx/cli.py --help).
"""
from __future__ import annotations

import os
import sys

# make the fx package importable regardless of cwd
_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

# ---- legacy re-exports (kept 1:1 for old importers) -------------------------
from fx.core import (  # noqa: E402,F401
    ALT_ENTER, ALT_LEAVE, CLEAR, CLEAR_SCROLL, HIDE, HOME, NOWRAP, RESET, SHOW,
    WRAP, enable_vt, rgb, term_size,
)
from fx.base import FrameCtx  # noqa: E402
from fx.effects.sphere import sphere_frame  # noqa: E402,F401
from fx.effects.plasma import plasma_frame  # noqa: E402,F401
from fx.effects.rain import Rain  # noqa: E402,F401
from fx.effects.text3d import FONT, big_text, block_text, hgrad  # noqa: E402,F401
from fx import cli as _fx_cli  # noqa: E402


def run(render, fps=30, seconds=None):
    """Legacy driver: ``render(t) -> frame string`` inside the safe play loop."""
    from fx.core import play
    from fx.theme import get_theme

    class _CallableEffect:
        name = "_legacy"

        def setup(self):
            pass

        def teardown(self):
            pass

        def render(self, ctx):
            return render(ctx.t)

    from fx.core import resolve_size
    w, h = resolve_size()
    play(_CallableEffect(), fps=fps, seconds=seconds,
         ctx_factory=lambda t, i: FrameCtx(t=t, frame_index=i, width=w,
                                           height=h, theme=get_theme(None)))


def render_once(frame_str):
    """Legacy one-shot: print a pre-rendered frame to the normal screen."""
    enable_vt()
    sys.stdout.write(frame_str)
    sys.stdout.write(RESET + "\n")
    sys.stdout.flush()


# ---- legacy CLI -> new fx CLI translation -----------------------------------
def _parse_legacy(argv):
    import argparse
    p = argparse.ArgumentParser(
        prog="ascii_fx.py",
        description="Terminal visual effects (legacy shim; see fx/cli.py).")
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--seconds", type=float, default=None)
    p.add_argument("--once", action="store_true")
    p.add_argument("--width", type=int, default=0)
    p.add_argument("--height", type=int, default=0)
    sub = p.add_subparsers(dest="effect", required=True)

    sp = sub.add_parser("sphere")
    sp.add_argument("--color", action="store_true")
    sp.add_argument("--tint", default="50DCC8")
    sp.add_argument("--speed", type=float, default=1.0)

    pl = sub.add_parser("plasma", aliases=["wave"])
    pl.add_argument("--palette", choices=["hsv", "rgb"], default="hsv")

    rn = sub.add_parser("rain")
    rn.add_argument("--head", default="C8FFC8")
    rn.add_argument("--hue", default="00FF00")

    tx = sub.add_parser("text3d")
    tx.add_argument("text")
    tx.add_argument("--from", dest="c0", default="FF5000")
    tx.add_argument("--to", dest="c1", default="00B4FF")
    tx.add_argument("--shimmer", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_legacy(argv if argv is not None else sys.argv[1:])

    new: list[str] = ["play"]
    sets: list[str] = []
    if args.effect == "sphere":
        new.append("sphere")
        sets.append(f"speed={args.speed}")
        if args.color:
            sets.append(f"tint={args.tint}")
        else:
            sets.append("mono=true")
    elif args.effect in ("plasma", "wave"):
        new.append("plasma")
        sets.append(f"palette={args.palette}")
    elif args.effect == "rain":
        new.append("rain")
        sets.append(f"head={args.head}")
        sets.append(f"hue={args.hue}")
    elif args.effect == "text3d":
        new.append("text3d")
        sets.append(f"text={args.text}")
        sets.append(f"from={args.c0}")
        sets.append(f"to={args.c1}")
        if args.shimmer:
            sets.append("shimmer=true")

    for s in sets:
        new.extend(["--set", s])
    if args.fps:
        new.extend(["--fps", str(args.fps)])
    if args.once:
        new.append("--once")
    elif args.seconds is not None:
        new.extend(["--seconds", str(args.seconds)])
    else:
        new.append("--forever")  # legacy default: run until Ctrl-C
    if args.width:
        new.extend(["--width", str(args.width)])
    if args.height:
        new.extend(["--height", str(args.height)])

    return _fx_cli.main(new)


if __name__ == "__main__":
    sys.exit(main())
