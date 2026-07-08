"""fx CLI: list | show | play | gallery | random.

Run as a package (``python -m fx ...`` from skills/cmd-art) or directly by
path (``python skills/cmd-art/fx/cli.py ...``) -- the PEP-366 prelude below
makes the direct-path form work from any cwd.

Safety contract: ``play`` is BOUNDED by default (10s when no --seconds/--frames
given on a TTY; pass --forever for an explicit unbounded run), degrades to a
single plain frame when stdout is not a TTY, and always restores the terminal
(cursor, wrap, alt-screen) via the try/finally in fx.core.play.
"""
from __future__ import annotations

import os
import sys

if __package__ in (None, ""):  # executed by path: bootstrap the fx package
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "fx"
    import fx  # noqa: F401  (initialize the package so relative imports bind)

import argparse
import json
import random as _random

from . import registry
from .base import Effect, FrameCtx
from .core import is_tty, play, render_once, resolve_size
from .show import Segment, Show, parse_script, parse_seq
from .theme import DEFAULT_THEME, THEMES, get_theme, theme_names

DEFAULT_BOUND_SECONDS = 10.0


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _parse_set(pairs: list[str]) -> dict:
    out = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise SystemExit(f"error: --set expects key=value, got {raw!r}")
        k, v = raw.split("=", 1)
        out[k.strip()] = v
    return out


def _resolve_theme(name: str | None, eff_cls: type[Effect]):
    if name:
        key = name.lower().strip()
        if key not in THEMES:
            raise SystemExit(
                f"error: unknown theme {name!r}. Themes: {', '.join(theme_names())}")
        return THEMES[key]
    return get_theme(eff_cls.preferred_theme)


def _bounds(args) -> tuple:
    """(seconds, frames) for the play loop, honoring the bounded-by-default rule."""
    if getattr(args, "forever", False):
        return None, None
    seconds = getattr(args, "seconds", None)
    frames = getattr(args, "frames", None)
    if seconds is None and frames is None:
        return DEFAULT_BOUND_SECONDS, None
    return seconds, frames


def _run_effect(eff_cls: type[Effect], args) -> int:
    params = eff_cls.parse_params(_parse_set(args.set))
    theme = _resolve_theme(args.theme, eff_cls)
    width, height = resolve_size(args.width or None, args.height or None)
    effect = eff_cls()

    def ctx_factory(t, frame_index):
        return FrameCtx(t=t, frame_index=frame_index, width=width,
                        height=height, theme=theme, params=params)

    if args.once or not eff_cls.is_animated(params):
        render_once(effect, ctx_factory=ctx_factory)
        return 0
    seconds, frames = _bounds(args)
    play(effect, fps=args.fps or eff_cls.default_fps, seconds=seconds,
         frames=frames, ctx_factory=ctx_factory)
    return 0


def _add_play_flags(sp, fps_default=None):
    sp.add_argument("--theme", help=f"palette ({', '.join(theme_names())})")
    sp.add_argument("--seconds", type=float, default=None,
                    help=f"stop after N seconds (default {DEFAULT_BOUND_SECONDS:g})")
    sp.add_argument("--frames", type=int, default=None, help="stop after N frames")
    sp.add_argument("--once", action="store_true",
                    help="render ONE frame to the normal screen and exit")
    sp.add_argument("--forever", action="store_true",
                    help="run until Ctrl-C (explicitly unbounded)")
    sp.add_argument("--fps", type=float, default=fps_default,
                    help="frame rate (default: effect's own)")
    sp.add_argument("--width", type=int, default=0, help="0 = terminal width")
    sp.add_argument("--height", type=int, default=0, help="0 = terminal height - 1")
    sp.add_argument("--set", action="append", metavar="K=V", default=[],
                    help="effect parameter override (repeatable)")


# --------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------
def cmd_list(args) -> int:
    effects = registry.by_tag(args.tag) if args.tag else registry.all_effects()
    if args.json:
        out = [{
            "name": c.name, "description": c.description,
            "tags": list(c.tags), "aliases": list(c.aliases),
            "animated": c.animated,
            "preferred_theme": c.preferred_theme,
            "params": [{"name": p.name, "kind": p.kind, "default": p.default,
                        "help": p.help,
                        **({"choices": list(p.choices)} if p.choices else {}),
                        **({"min": p.min} if p.min is not None else {}),
                        **({"max": p.max} if p.max is not None else {})}
                       for p in c.params],
        } for c in effects]
        print(json.dumps(out, indent=2))
    else:
        if not effects:
            print(f"no effects match tag {args.tag!r}")
            return 1
        wname = max(len(c.name) for c in effects)
        for c in effects:
            kind = "anim  " if c.animated else "static"
            tags = ",".join(c.tags)
            alias = f" (alias: {', '.join(c.aliases)})" if c.aliases else ""
            print(f"{c.name:<{wname}}  {kind}  [{tags}]  {c.description}{alias}")
    for mod, _tb in registry.load_errors():
        print(f"warning: {mod} failed to import (run 'show' on it for details)",
              file=sys.stderr)
    return 0


def cmd_show(args) -> int:
    # Sequence-player form: show --seq / --script
    if args.seq or args.script:
        segments = parse_seq(args.seq, args.seconds_per) if args.seq \
            else parse_script(args.script, args.seconds_per)
        return _play_show(segments, args)
    if not args.name:
        raise SystemExit("error: show needs an effect name, --seq, or --script")
    try:
        cls = registry.get(args.name)
    except KeyError as exc:
        raise SystemExit(f"error: {exc.args[0]}")
    print(f"{cls.name} -- {cls.description}")
    print(f"  animated: {'yes' if cls.animated else 'no (static, normal screen)'}"
          f"    tags: {', '.join(cls.tags) or '-'}"
          f"    aliases: {', '.join(cls.aliases) or '-'}")
    if cls.preferred_theme:
        print(f"  preferred theme: {cls.preferred_theme}")
    if cls.params:
        print("  params (--set key=value):")
        for p in cls.params:
            rng = ""
            if p.min is not None or p.max is not None:
                rng = f"  [{p.min if p.min is not None else ''}..{p.max if p.max is not None else ''}]"
            ch = f"  {{{','.join(map(str, p.choices))}}}" if p.choices else ""
            print(f"    {p.name:<10} {p.kind:<6} default={p.default!r}{ch}{rng}  {p.help}")
    else:
        print("  params: none")
    mode = "--once" if not cls.animated else "--seconds 5"
    print(f"  example: python fx/cli.py play {cls.name} {mode}"
          + (f" --theme {cls.preferred_theme}" if cls.preferred_theme else ""))
    return 0


def _play_show(segments: list[Segment], args) -> int:
    width, height = resolve_size(args.width or None, args.height or None)
    theme = get_theme(args.theme or DEFAULT_THEME)
    if args.theme:
        theme = _resolve_theme(args.theme, Effect)
    show = Show(segments)
    if not is_tty():
        # No TTY: render the first segment once, plainly.
        seg = segments[0]
        params = seg.params or type(seg.effect).param_defaults()
        render_once(seg.effect, ctx_factory=lambda t, i: FrameCtx(
            t=t, frame_index=i, width=width, height=height,
            theme=seg.theme or theme, params=params))
        return 0
    show.play(width=width, height=height, theme=theme, fps=args.fps or 30.0)
    return 0


def cmd_play(args) -> int:
    try:
        cls = registry.get(args.name)
    except KeyError as exc:
        raise SystemExit(f"error: {exc.args[0]}")
    try:
        return _run_effect(cls, args)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")


def cmd_gallery(args) -> int:
    effects = registry.by_tag(args.tag) if args.tag else registry.all_effects()
    animated = [c for c in effects if c.animated]
    if not animated:
        raise SystemExit("error: no animated effects to tour")
    names = theme_names()
    segments = []
    for i, cls in enumerate(animated):
        theme = get_theme(cls.preferred_theme or names[i % len(names)])
        segments.append(Segment(effect=cls(), seconds=args.seconds_per,
                                theme=theme, params=cls.param_defaults(),
                                label=cls.name))
    print(f"gallery: {len(segments)} effects x {args.seconds_per:g}s "
          f"(total ~{len(segments) * args.seconds_per:g}s)", file=sys.stderr)
    return _play_show(segments, args)


def cmd_random(args) -> int:
    animated = [c for c in registry.all_effects() if c.animated]
    cls = _random.choice(animated)
    args.theme = args.theme or _random.choice(theme_names())
    print(f"random pick: {cls.name} / theme {args.theme}", file=sys.stderr)
    if args.seconds is None and args.frames is None and not args.forever:
        args.seconds = 8.0
    args.once = False
    return _run_effect(cls, args)


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fx",
        description="Pluggable terminal visual effects (truecolor, stdlib).")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list", help="list all registered effects")
    sp.add_argument("--tag", help="filter by tag (e.g. 3d, text, particles)")
    sp.add_argument("--json", action="store_true", help="machine-readable output")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser(
        "show",
        help="effect details (show NAME) or play a scripted show (--seq/--script)")
    sp.add_argument("name", nargs="?", help="effect name for details")
    sp.add_argument("--seq", help='sequence spec "effect[:theme[:sec]],..." '
                                  '("a|b" splits the screen)')
    sp.add_argument("--script", help="path to a JSON show script")
    sp.add_argument("--seconds-per", type=float, default=4.0,
                    help="default seconds per segment (default 4)")
    sp.add_argument("--theme", help="fallback theme for segments without one")
    sp.add_argument("--fps", type=float, default=None)
    sp.add_argument("--width", type=int, default=0)
    sp.add_argument("--height", type=int, default=0)
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("play", help="play one effect (bounded by default)")
    sp.add_argument("name", help="effect name or alias")
    _add_play_flags(sp)
    sp.set_defaults(func=cmd_play)

    sp = sub.add_parser("gallery", help="tour every animated effect in sequence")
    sp.add_argument("--seconds-per", type=float, default=3.0,
                    help="seconds per effect (default 3)")
    sp.add_argument("--tag", help="only effects with this tag")
    sp.add_argument("--theme", help="force one theme for the whole tour")
    sp.add_argument("--fps", type=float, default=None)
    sp.add_argument("--width", type=int, default=0)
    sp.add_argument("--height", type=int, default=0)
    sp.set_defaults(func=cmd_gallery)

    sp = sub.add_parser("random", help="play a random effect with a random theme")
    _add_play_flags(sp)
    sp.set_defaults(func=cmd_random)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    registry.load_all()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
