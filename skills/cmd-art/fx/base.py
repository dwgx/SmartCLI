"""Effect base classes: the contract every effect implements.

An :class:`Effect` is a pure frame producer: ``render(ctx) -> str`` returns one
complete frame (``ctx.height`` rows joined by ``\\n``, no trailing newline, every
cell written). The play loop in :mod:`fx.core` owns the terminal; effects never
print, sleep, or touch ANSI modes themselves. State (particles, buffers) lives on
the instance, initialised in :meth:`Effect.setup` and released in
:meth:`Effect.teardown`.

Parameters are declared as :class:`Param` descriptors so the CLI can list, parse
and validate ``--set key=value`` pairs without knowing effect internals.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional

from .theme import Theme, get_theme

# Default dark->bright ASCII luminance ramp (shared by many effects).
DEFAULT_RAMP = " .:-=+*#%@"


# --------------------------------------------------------------------------
# Parameter schema
# --------------------------------------------------------------------------
_TRUE = {"1", "true", "yes", "on", "y"}
_FALSE = {"0", "false", "no", "off", "n"}


def parse_hex_color(s: str) -> tuple[int, int, int]:
    """``'#RRGGBB'`` / ``'RRGGBB'`` -> RGB int triple. Raises ValueError when malformed."""
    h = s.strip().lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected 6-digit hex color, got {s!r}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


@dataclass(frozen=True)
class Param:
    """One declared effect parameter (name, type, default, constraints, help).

    ``kind`` is one of ``int float str bool color``. ``color`` accepts hex text
    and coerces to an RGB triple; empty string means "unset" and yields None.
    """

    name: str
    kind: str = "str"
    default: Any = None
    help: str = ""
    choices: Optional[tuple] = None
    min: Optional[float] = None
    max: Optional[float] = None

    def coerce(self, raw: Any) -> Any:
        """Parse+validate a raw (usually string) value into the declared type."""
        if raw is None:
            return self.default
        v: Any
        if self.kind == "int":
            s = str(raw).strip()
            # Accept 0x/0o/0b prefixed literals AND plain (possibly zero-padded)
            # decimals like "08"/"010" — base 0 alone rejects the latter, which is
            # a confusing footgun for a CLI user typing a leading-zero number.
            try:
                low = s.lower()
                if low[:2] in ("0x", "0o", "0b") or low[:3] in ("-0x", "-0o", "-0b"):
                    v = int(s, 0)
                else:
                    v = int(s, 10)
            except ValueError:
                raise ValueError(f"param {self.name!r}: not an integer: {raw!r}")
        elif self.kind == "float":
            v = float(raw)
        elif self.kind == "bool":
            if isinstance(raw, bool):
                v = raw
            else:
                s = str(raw).strip().lower()
                if s in _TRUE:
                    v = True
                elif s in _FALSE:
                    v = False
                else:
                    raise ValueError(f"param {self.name}: not a bool: {raw!r}")
        elif self.kind == "color":
            if isinstance(raw, tuple):
                v = raw
            elif str(raw).strip() == "":
                v = None
            else:
                v = parse_hex_color(str(raw))
        else:  # str
            v = str(raw)
        if self.choices is not None and v not in self.choices:
            raise ValueError(
                f"param {self.name}: {v!r} not in {list(self.choices)}")
        if self.min is not None and isinstance(v, (int, float)) and v < self.min:
            raise ValueError(f"param {self.name}: {v} < min {self.min}")
        if self.max is not None and isinstance(v, (int, float)) and v > self.max:
            raise ValueError(f"param {self.name}: {v} > max {self.max}")
        return v


# --------------------------------------------------------------------------
# Frame context
# --------------------------------------------------------------------------
@dataclass
class FrameCtx:
    """Everything an effect may read while rendering one frame."""

    t: float                 # seconds since play started
    frame_index: int         # 0-based frame counter
    width: int               # target frame width in cells
    height: int              # target frame height in rows
    theme: Theme             # active palette (never None)
    params: dict = field(default_factory=dict)  # coerced effect params


# --------------------------------------------------------------------------
# Effect ABC
# --------------------------------------------------------------------------
class Effect(ABC):
    """Abstract base for all effects.

    Class metadata (override in subclasses):
        name: registry key, lowercase, unique.
        description: one-line summary shown by ``list``/``show``.
        tags: free-form labels for ``by_tag`` filtering (e.g. "3d", "text").
        aliases: alternate registry names (e.g. plasma <- "wave").
        params: declared :class:`Param` schema.
        animated: False for one-shot art (see :class:`StaticEffect`).
        preferred_theme: theme used when the caller does not pick one.
        default_fps: hint for the play loop.
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    tags: ClassVar[tuple[str, ...]] = ()
    aliases: ClassVar[tuple[str, ...]] = ()
    params: ClassVar[tuple[Param, ...]] = ()
    animated: ClassVar[bool] = True
    preferred_theme: ClassVar[Optional[str]] = None
    default_fps: ClassVar[float] = 30.0

    # -- lifecycle hooks (state allocation) ---------------------------------
    def setup(self) -> None:
        """Called once before the first frame. Allocate buffers/particles here."""

    def teardown(self) -> None:
        """Called after the last frame, ALSO on error/Ctrl-C. Release state here."""

    # -- rendering -----------------------------------------------------------
    @abstractmethod
    def render(self, ctx: FrameCtx) -> str:
        """Return one full frame: ``ctx.height`` rows joined by newlines."""

    def default_ctx(self, t: float = 0.7, frame_index: int = 0) -> FrameCtx:
        """Fallback ctx for bare ``render_once`` calls (tests, previews)."""
        from .core import resolve_size
        w, h = resolve_size()
        return FrameCtx(t=t, frame_index=frame_index, width=w, height=h,
                        theme=get_theme(self.preferred_theme),
                        params=self.param_defaults())

    # -- parameter helpers ----------------------------------------------------
    @classmethod
    def param_defaults(cls) -> dict:
        return {p.name: p.default for p in cls.params}

    @classmethod
    def parse_params(cls, pairs: dict) -> dict:
        """Coerce+validate a raw ``{name: value}`` mapping against the schema.

        Unknown keys raise ValueError so typos fail loudly instead of being
        silently ignored.
        """
        schema = {p.name: p for p in cls.params}
        out = cls.param_defaults()
        for key, raw in pairs.items():
            if key not in schema:
                known = ", ".join(sorted(schema)) or "(none)"
                raise ValueError(
                    f"effect {cls.name!r} has no param {key!r} (known: {known})")
            out[key] = schema[key].coerce(raw)
        return out

    @classmethod
    def is_animated(cls, params: dict) -> bool:
        """Whether this effect should run in the play loop given *params*.

        Override for effects that are static by default but can animate
        (e.g. text3d with shimmer=true).
        """
        return cls.animated


class StaticEffect(Effect):
    """Single-frame art (banners, image conversion): rendered on the NORMAL
    screen via ``render_once`` -- no alt-screen, no loop, output stays in the
    scrollback. ``play`` treats these as one-shot regardless of --seconds."""

    animated: ClassVar[bool] = False
