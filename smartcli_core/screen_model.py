"""Thin wrapper over ``pyte`` that turns a byte stream into an inspectable grid.

:class:`ScreenModel` owns a single long-lived ``pyte.ByteStream`` + ``pyte.Screen``
pair. Feed raw PTY bytes with :meth:`feed`; the stream is stateful and stream-safe
so partial ANSI escapes and split multibyte UTF-8 across reads are handled
correctly. Never recreate the stream per read.

Exposes plain text (``pyte.screen.display``), the cursor, a stability hash, and a
per-cell attribute reader that copes with the sparse dict-of-dicts buffer.

It also enforces the perception chain's rule for a control sequence it does not
understand: reject it, never guess at it (see :data:`UNKNOWN_SEQUENCE_POLICY`).
"""

from __future__ import annotations

import unicodedata
import zlib
from collections.abc import Callable, Mapping
from enum import Enum
from types import MappingProxyType
from typing import NamedTuple

import pyte
from pyte import modes as mo
from pyte.screens import Char

from wcwidth import wcwidth as wcwidth_cached  # pyte's own width dependency


def _pyte_dch_handles_wide() -> bool:
    """Does the installed ``pyte`` already widen DCH over a two-column glyph?

    Unlike the alternate screen there is no attribute to test for, so this asks
    the question behaviourally, once, on a throwaway 4x1 screen: delete the wide
    glyph in ``中x`` and see whether ``x`` ends up at column 0 (the stub travelled
    with its base) or vanishes.

    It exists because ``_Screen.delete_characters`` widens the count itself, and
    doing that on top of a pyte that already does it deletes one cell too many —
    silently eating a character. With ``pyte>=0.8.1`` unpinned, that would arrive
    as a dependency upgrade, not a code change. Measured against a pyte carrying
    the fix: the override turned ``"x"`` into ``""``.
    """
    try:
        probe = pyte.Screen(4, 1)
        pyte.ByteStream(probe).feed("\u4e2dx".encode() + b"\r\x1b[1P")
        return probe.buffer[0][0].data == "x"
    except Exception:
        # Never let a probe break import; the override is correct for every
        # released pyte, so assume the historical behaviour on doubt.
        return False


#: Evaluated once at import: see _pyte_dch_handles_wide.
_PYTE_DCH_HANDLES_WIDE: bool = _pyte_dch_handles_wide()


def _sgr_rewrite_params(params: bytes) -> bytes | None:
    """Rewrite a colon-bearing CSI SGR parameter list into pyte's dialect.

    Returns the new parameter bytes, or ``None`` when every group is something
    pyte cannot represent and the WHOLE sequence must be dropped. Dropping the
    sequence rather than emitting ``ESC[m`` matters: an empty parameter list is
    a full attribute reset, so "drop the unsupported attribute" would silently
    become "reset the cursor attributes".

    Only ITU T.416 forms with a known meaning are rewritten. An unknown
    sub-parameter group is dropped as a group -- its numbers must never be
    re-emitted as bare SGR codes, because ``4:3`` naively flattened to ``4;3``
    means "underline + italic" and ``58:2::1:2:3`` flattened to ``58;2;;1;2;3``
    means "dim + bold + dim + italic" (58 is unknown to pyte and ignored).
    """
    kept: list[bytes] = []
    for group in params.split(b";"):
        if b":" not in group:
            kept.append(group)          # ordinary SGR code: untouched
            continue
        parts = group.split(b":")
        head = parts[0]
        if head == b"4":
            # 4:n is the underline STYLE (4:0 off, 4:1..4:5 single/double/
            # curly/dotted/dashed). pyte knows only basic underline, so the
            # style degrades to 4 -- never to a bare "3", which is italic.
            subs = [p for p in parts[1:] if p]
            kept.append(b"24" if subs and set(subs) == {b"0"} else b"4")
        elif (head in (b"38", b"48") and len(parts) >= 5 and parts[1] == b"2"
              and all(p.isdigit() for p in parts[-3:])):
            # 38:2:<colour-space>:R:G:B -> 38;2;R;G;B. The colour-space slot is
            # optional and is usually empty ("38:2::255:0:128"); pyte's 24-bit
            # path pops exactly three values, so the slot has to disappear
            # instead of becoming an empty parameter.
            kept.append(head + b";2;" + b";".join(parts[-3:]))
        elif head in (b"38", b"48") and len(parts) == 3 and parts[1] == b"5" and parts[2].isdigit():
            kept.append(head + b";5;" + parts[2])       # 38:5:n
        else:
            continue                    # 58 underline colour, and every unknown form
    if not kept and params:
        return None
    return b";".join(kept)


class Mode(str, Enum):
    """The CLOSED set of terminal modes this screen model can be asked about.

    A ``str`` enum on purpose: ``Mode.ALT_SCREEN == "alt_screen"`` and
    :meth:`ScreenModel.mode` accepts either spelling, so callers can write the
    name literally (``model.mode("alt_screen")``) without importing anything,
    while the type keeps the set closed — a name that is not a member raises
    instead of quietly answering ``False``.

    Membership rule: a member is a *state a caller can observe*, i.e. "is the
    terminal in this mode right now". That is what excludes DEC private mode
    1048 (save/restore cursor): it is a save and a restore, two operations
    rather than a state, so there is no honest boolean for it. It stays
    private to :class:`_Screen` (``_CURSOR_ONLY_MODE``) where it is acted on.

    The names are the ones a driving agent can act on or must not misread:
    key-transmission form (:attr:`APP_CURSOR`), buffer ownership
    (:attr:`ALT_SCREEN`), and the modes pyte itself branches on while parsing,
    because each one silently changes what later bytes MEAN.
    """

    ALT_SCREEN = "alt_screen"
    APP_CURSOR = "app_cursor"
    AUTOWRAP = "autowrap"
    COLUMN_132 = "column_132"
    CURSOR_VISIBLE = "cursor_visible"
    INSERT_MODE = "insert_mode"
    NEWLINE_MODE = "newline_mode"
    ORIGIN = "origin"
    REVERSE_VIDEO = "reverse_video"

    def __repr__(self) -> str:
        return f"Mode.{self.name}"


class ModeSpec(NamedTuple):
    """One entry of :data:`MODE_REGISTRY`: what to read, and where from.

    ``numbers`` is every mode number that puts the terminal into this state, as
    the program writes it — ``ESC[?1049h`` arrives as ``1049``. It is a tuple
    because the alternate screen is entered by three of them (47, 1047, 1049:
    1049 being 1047 plus the cursor save). Where pyte exports a constant the
    number is derived from it (:func:`_dec`) rather than typed in, so the
    registry cannot drift from the pyte it is reading.

    ``private`` says whether the sequence carries the ``?`` (DEC private).
    pyte stores private modes pre-shifted left by five so they cannot collide
    with the ANSI ones, which is why :attr:`Mode.APP_CURSOR` resolves to the
    otherwise-magic ``1 << 5``.

    ``probe`` is set only for modes that are NOT a bit in ``Screen.mode``:
    :attr:`Mode.ALT_SCREEN` is our own buffer state (:attr:`_Screen.alt_screen`
    reads through to the base class when pyte implements it) and
    :attr:`Mode.CURSOR_VISIBLE` is read from the cursor itself. Both are asked
    "what is true now", which is the same question the bit answers for the
    rest — the difference is only where pyte happens to keep the answer.
    """

    numbers: tuple[int, ...]
    private: bool = True
    probe: Callable[[pyte.Screen], bool] | None = None

    @property
    def bit(self) -> int:
        """The value this mode occupies in ``pyte.Screen.mode``."""
        if len(self.numbers) != 1:
            raise ValueError(f"{self.numbers} is not a single Screen.mode bit")
        return self.numbers[0] << 5 if self.private else self.numbers[0]

    def resolve(self, screen: pyte.Screen) -> bool:
        """Is this mode set on ``screen`` right now?"""
        if self.probe is not None:
            return bool(self.probe(screen))
        return self.bit in screen.mode


def _dec(constant: int) -> int:
    """The DEC mode number behind one of pyte's private-mode constants.

    pyte stores private modes shifted left by five (``pyte.modes`` says so, and
    names DECOM ``192`` rather than ``6``); :attr:`ModeSpec.bit` shifts back.
    Un-shifting pyte's own constant rather than typing the number keeps the two
    in step: ``tests/test_terminal_modes.py`` asserts ``bit == mo.DECAWM`` for
    every mode pyte exports, so a wrong shift there is a failure, not a silently
    different query.
    """
    return constant >> 5


#: The registry the query API reads. One entry per :class:`Mode`, so a member
#: without a spec is impossible by construction and a spec without a member is
#: a lookup error rather than a silently unreachable mode.
MODE_REGISTRY: Mapping[Mode, ModeSpec] = MappingProxyType({
    # 47/1047/1049 all switch buffers; only 1049 also saves the cursor, which
    # _Screen._enter_alt distinguishes. Read as a probe because pyte sets the
    # bit for 1047 and never clears it, so the bit is not the state (verified:
    # `?1047h ?1049l` leaves 1047's bit set while the primary buffer is back).
    # `getattr` rather than `s.alt_screen`: that attribute is OURS (or a future
    # pyte's), so a stock pyte.Screen does not have it — the same reason
    # _Screen.alt_screen reads its base attribute through getattr. The default
    # is False, which is right for a screen that never entered an alternate
    # buffer, and mypy needs the getattr to see that.
    Mode.ALT_SCREEN: ModeSpec((47, 1047, 1049),
                              probe=lambda s: bool(getattr(s, "alt_screen", False))),
    Mode.APP_CURSOR: ModeSpec((1,)),                        # DECCKM (pyte exports none)
    Mode.AUTOWRAP: ModeSpec((_dec(mo.DECAWM),)),            # DECAWM
    Mode.COLUMN_132: ModeSpec((_dec(mo.DECCOLM),)),         # DECCOLM
    # DECTCEM. Read from the cursor because that is what "visible" means, and
    # because it is the attribute the existing `cursor_hidden` exposed.
    Mode.CURSOR_VISIBLE: ModeSpec((_dec(mo.DECTCEM),),
                                  probe=lambda s: not s.cursor.hidden),
    Mode.INSERT_MODE: ModeSpec((mo.IRM,), private=False),   # IRM (ANSI, no `?`)
    Mode.NEWLINE_MODE: ModeSpec((mo.LNM,), private=False),  # LNM (ANSI, no `?`)
    Mode.ORIGIN: ModeSpec((_dec(mo.DECOM),)),               # DECOM
    Mode.REVERSE_VIDEO: ModeSpec((_dec(mo.DECSCNM),)),      # DECSCNM
})


# ---------------------------------------------------------------------------
# The mouse MODE, read where pyte records it.
#
# This is deliberately NOT a member of :class:`Mode`. That enum's contract is
# "a member is a single bit in ``Screen.mode``", with exactly two documented
# exceptions (the alternate buffer and the cursor, neither of which is a bit).
# Mouse reporting is NINE private mode numbers with no single bit: 9/1000/1002/
# 1003 say what is tracked, 1005/1015/1006/1016 say how the coordinates are
# encoded. ``ModeSpec`` cannot express that — ``bit`` raises on a multi-number
# spec rather than pick one number and report a mode that is never set as
# permanently on — so folding it in would mean a third probe in a set whose
# two existing probes are individually justified, for a state that is not the
# same kind of thing. It is a separate query, over the same storage, using the
# same shift: private modes live in ``Screen.mode`` pre-shifted left by five
# (:attr:`ModeSpec.bit`).
# ---------------------------------------------------------------------------

#: DEC private mode numbers that mean "this program is receiving mouse events",
#: mapped to the report ENCODING that number selects.
#:
#: 9 is the original X10 tracking mode and 1000/1002/1003 are the VT200 tracking
#: modes; all four carry the X10 encoding unless one of the coordinate encodings
#: is also set. 1005 (utf8) and 1015 (urxvt) change the encoding, not what is
#: tracked. 1016 is the SGR encoding measured in PIXELS.
#:
#: 2004 (focus reporting) is deliberately ABSENT. It is enabled alongside mouse
#: tracking often enough that counting it would report a live mouse on a program
#: that only ever asked to be told about focus — a false "the mouse is live" is
#: exactly the kind of guess this module refuses to make.
MOUSE_REPORTING_MODES: Mapping[int, str] = MappingProxyType({
    9: "x10",
    1000: "x10",
    1002: "x10",
    1003: "x10",
    1005: "urxvt",
    1015: "urxvt",
    1006: "sgr",
    1016: "sgr-pixel",
})


#: pyte stores DEC private modes pre-shifted left by five, so that they cannot
#: collide with the ANSI ones. Derived from the registry's own arithmetic
#: (:attr:`ModeSpec.bit` divides back out) rather than typed as a second literal
#: here: two copies of the shift are two copies to drift.
_PRIVATE_MODE_SHIFT: int = (
    MODE_REGISTRY[Mode.APP_CURSOR].bit // MODE_REGISTRY[Mode.APP_CURSOR].numbers[0]
).bit_length() - 1


class MouseReport(NamedTuple):
    """What the driven program last asked for, read from the MODE and not from
    a report.

    Every field is a fact about what the program *enabled*, which is the only
    part of a mouse interaction an agent can trust: the reports themselves are
    consumed and discarded, because a report drawn or guessed at corrupts the
    grid (see :data:`UNKNOWN_SEQUENCE_POLICY`).
    """

    #: Is any tracking mode set? A program that has enabled reporting expects
    #: events, so a click may land at any moment and an agent must not assume
    #: the screen is only ever changed by the program.
    enabled: bool
    #: The mode numbers currently set, e.g. ``(1006,)``. Read this against
    #: :data:`MOUSE_REPORTING_MODES` for the encoding each one selects.
    modes: tuple[int, ...]
    #: ``True`` when a report's coordinates are CELL indices, ``False`` when
    #: they are PIXELS, and ``None`` when nothing is reporting OR when the unit
    #: is genuinely ambiguous.
    #:
    #: That last case is the reason this is a field and not a bool. 1006 (SGR)
    #: and 1016 (SGR-pixels) produce BYTE-IDENTICAL reports and differ only in
    #: what the numbers mean, and both may be set at once — in which case only
    #: the order they were set in disambiguates them, and we do not track that.
    #: A consumer that assumed cells on a 1016 application would act on a row
    #: that does not exist. ``None`` means REFUSE, not "assume cells".
    cells: bool | None


def _mouse_report(screen: pyte.Screen) -> MouseReport:
    """Read the mouse reporting state off ``screen``'s mode set."""
    mode = getattr(screen, "mode", ())
    active = tuple(n for n in MOUSE_REPORTING_MODES
                   if n << _PRIVATE_MODE_SHIFT in mode)
    if not active:
        return MouseReport(enabled=False, modes=(), cells=None)
    encodings = {MOUSE_REPORTING_MODES[n] for n in active}
    # A tracking mode (9/1000/1002/1003) says WHAT is reported; the encoding
    # modes say HOW, and 1006/1016 replace the encoding without contradicting
    # the tracking mode. So `1000h 1006h` is the ordinary cell-reporting
    # combination, not a contradiction. The only genuine ambiguity is 1006
    # together with 1016: same bytes, opposite units, and which one won depends
    # on the order they were set, which this does not record.
    if "sgr" in encodings and "sgr-pixel" in encodings:
        cells: bool | None = None        # refuse: the unit is not knowable
    elif "sgr-pixel" in encodings:
        cells = False
    else:
        cells = True            # sgr, x10 and urxvt all report CELLS
    return MouseReport(enabled=True, modes=active, cells=cells)


# ---------------------------------------------------------------------------
# REJECT-DON'T-GUESS: what the perception chain does with a control sequence it
# does not understand. One statement, one place, applied by
# _ByteStream._disposition.
#
# Three times now the same failure has recurred in three unrelated families:
# SGR colon sub-parameters (drawn as the literal text "3mU"), DCS/APC graphics
# payloads (kitty base64 read as content), and inbound mouse reports (drawn as
# "0;10;5M"). In every case the sequence was GUESSED AT — reinterpreted as
# something it resembled, or handed to a pyte entry point that was not written
# for its shape — and the grid was quietly wrong with no error signal, because
# pyte "parsed" all of them. So:
#
#   A control sequence this module does not understand is CONSUMED, never
#   interpreted. Consumed means read to its end, emitted to pyte as NOTHING,
#   counted in ScreenModel.unknown_sequences (with the reason in
#   ScreenModel.last_unknown), and recovery continues with the very next byte.
#
# It must NEVER:
#   * draw the bytes as text. Control debris on the grid is indistinguishable
#     from content an agent is supposed to read, and it corrupts the one thing
#     this module exists to provide.
#   * hand the sequence to a pyte entry point that was not written for its
#     shape. pyte dispatches on the FINAL BYTE alone, so a report whose final
#     byte collides with a real command is "parsed" into that command with the
#     wrong arity, raises, and ScreenModel.feed swallows the raise — so the REST
#     OF THAT OUTPUT BATCH IS DROPPED. Silent content loss is worse than a
#     dropped sequence, which is why this is a hard rule and not a style note.
#   * wedge the stream. An open sequence is bounded by
#     UNKNOWN_SEQUENCE_POLICY.cap and recovered by the existing
#     swallow-to-final-byte path, so a program emitting garbage cannot cost the
#     driver its screen.
#
# This is NOT an unbounded swallowing machine. A sequence is rejected only when
# we can name why it is not what it looks like; everything else is forwarded
# untouched, and an unrecognised sequence is always recoverable.
# ---------------------------------------------------------------------------


class UnknownSequencePolicy(NamedTuple):
    """The parts of "reject, don't guess" that are load-bearing.

    Kept as data rather than left as prose so a test can assert the rule
    instead of the comment that states it: a policy nobody can fail is a
    comment, and this repository's own history is three defects that a comment
    would not have stopped.
    """

    #: Bytes one open sequence may buffer before it is abandoned. Past the cap
    #: the filter swallows to the next final byte and shows what a terminal
    #: that gave up on an over-long sequence shows: nothing.
    cap: int
    #: Always False. A rejected sequence that reached the grid would be
    #: indistinguishable from content.
    draws_unknown_bytes_as_text: bool
    #: Always False. A shape mismatch raises inside pyte and the raise is
    #: swallowed, which loses the rest of the output batch.
    forwards_to_unmatched_pyte_entry: bool
    #: The observable the policy bumps instead of staying silent.
    counter: str


UNKNOWN_SEQUENCE_POLICY = UnknownSequencePolicy(
    cap=1024,
    draws_unknown_bytes_as_text=False,
    forwards_to_unmatched_pyte_entry=False,
    counter="unknown_sequences",
)

#: Parameter bytes pyte's own CSI parser carries through a sequence without
#: ending it early: digits, the ';' separator, the DEC private '?' marker, and
#: the '>' and space it explicitly skips (secondary DA). pyte's loop treats ANY
#: other byte as a final byte — it dispatches on it and returns to GROUND — so
#: everything after it is drawn as text. Two live families live in that gap: the
#: SGR 1006 mouse report (``ESC[<b;x;yM``, the '<' ends the sequence) and the
#: kitty keyboard protocol (``ESC[=1u``, the '=' does the same). Naming neither
#: here is the point: they are two instances of one rule.
_PYTE_CSI_PARAM_BYTES = frozenset(b"0123456789;? >")

#: How many parameters each pyte CSI entry point was written for, as
#: ``(non-private, private)``, keyed by the single-byte final byte. -1 is the
#: ``*args`` handler, which takes any number.
#:
#: Two numbers, not one, because pyte calls the private form differently
#: (streams.py: ``csi_dispatch[char](*params, private=True)``), so a keyword
#: named ``private`` eats one of the positional slots for that form only.
#: ``erase_in_line(how=0, private=False)`` is the single case in pyte where
#: that matters, and getting it wrong would be an arity rejection of a
#: two-parameter ``ESC[1;2K``.
#:
#: Read off the installed pyte's own signatures;
#: ``tests/test_unknown_sequences.py`` asserts this table against
#: ``pyte.Stream.csi`` and those signatures, so a pyte upgrade that changes an
#: arity fails instead of silently mis-joining.
_CSI_MAX_PARAMS: Mapping[bytes, tuple[int, int]] = MappingProxyType({
    b"'": (1, 1), b"@": (1, 1), b"A": (1, 1), b"B": (1, 1), b"C": (1, 1),
    b"D": (1, 1), b"E": (1, 1), b"F": (1, 1), b"G": (1, 1), b"H": (2, 2),
    b"J": (-1, -1), b"K": (2, 1), b"L": (1, 1), b"M": (1, 1), b"P": (1, 1),
    b"X": (1, 1), b"a": (1, 1), b"c": (1, 1), b"d": (1, 1), b"e": (1, 1),
    b"f": (2, 2), b"g": (1, 1), b"h": (-1, -1), b"l": (-1, -1), b"m": (-1, -1),
    b"n": (1, 1), b"r": (2, 2),
})

#: Finals whose pyte handler accepts the private form (``ESC[?...h``) — either
#: because it takes a ``private`` keyword or because it takes ``**kwargs``. For
#: every other final, pyte's parser calls ``handler(*params, private=True)`` and
#: the call raises, which is the same swallowed-raise path as an arity
#: mismatch: ``ESC[?6n`` (DECXCPR, a real query a real program sends) loses
#: every byte after it in that batch.
_CSI_PRIVATE_OK = frozenset((b"J", b"K", b"c", b"h", b"l"))
#: ECMA-48 control strings, keyed by the byte that follows ESC. pyte has no
#: branch for any of them -- its parser falls through to draw(), which is why
#: _ByteStream consumes their payloads instead of forwarding them.
#:
#: The NAME is all the counter can honestly report. Nothing buffers a payload
#: (that is the rule), so at the moment of the consume the filter has seen the
#: introducer and nothing else: claiming "sixel" or "kitty graphics" would be
#: reading ahead into bytes it deliberately does not hold. The family is the
#: honest unit, and it already separates the case that matters — a graphics
#: payload from yazi/chafa/viu/timg lands as DCS or APC.
_CONTROL_STRING_INTRODUCERS: Mapping[int, str] = MappingProxyType({
    0x50: "DCS",   # 'P' — sixel, DECRQSS
    0x58: "SOS",   # 'X'
    0x5E: "PM",    # '^' — xterm
    0x5F: "APC",   # '_' — kitty graphics, tmux passthrough
})


class _ByteStream(pyte.ByteStream):
    """``pyte.ByteStream`` with NEL dispatch and the REJECT-DON'T-GUESS policy.

    Every control sequence is classified by :meth:`_disposition` — the one
    place :data:`UNKNOWN_SEQUENCE_POLICY` is applied — before a single byte of
    it reaches pyte. Nothing here guesses.
    """

    escape = {**pyte.Stream.escape, "E": "next_line"}

    # SGR sub-parameters use ':' as the separator (ITU-T T.416): `ESC[4:3m` is a
    # curly underline, `ESC[38:2::R:G:Bm` a truecolor foreground. pyte's parser
    # does not know ':' at all, so it aborted the sequence and DREW THE REST AS
    # TEXT — `ESC[4:3mU` put the literal "3mU" on screen. Modern programs emit
    # this routinely (Neovim, kitty, delta), so an agent driving them read
    # escape-sequence debris as content. Measured against tmux 3.6b, which
    # renders just the styled character.
    #
    # The rewrite is therefore a STREAMING filter that runs in front of pyte:
    # it has to hold a sequence until its final byte arrives, because a PTY read
    # boundary lands inside an escape often (reads are chunked at the OS's
    # discretion), and it must rewrite only genuine CSI ... m sequences -- a
    # lookalike byte run inside an OSC/DCS string belongs to the application
    # (a window title may literally contain "ESC[4:3m") and must pass through
    # untouched. A whole-buffer regex cannot do either: it sees one chunk and
    # knows nothing about string state.
    #
    # States: GROUND -> (ESC) -> ESC_SEEN -> CSI | STRING | GROUND.
    #   * CSI collects its parameter bytes until a final byte (0x40-0x7E), then
    #     either forwards them unchanged or rewrites them via _sgr_rewrite_params.
    #   * an unterminated CSI is held for the next call up to _CSI_CAP bytes;
    #     past the cap the sequence is abandoned and its bytes are swallowed
    #     until the next final byte, so nothing is drawn as text and memory is
    #     bounded (a terminal that gave up on an over-long sequence shows the
    #     same thing: nothing).
    #   * STRING tracks OSC (`ESC]`, BEL or ST terminated) and DCS/SOS/PM/APC
    #     (`ESC P/X/^/_`, ST only) so their payloads are never rewritten, and so
    #     a lookalike inside one is never mistaken for a fresh sequence. No
    #     payload is ever buffered, whichever way it is disposed of below.
    #     The two families differ in what they are FORWARDED as. OSC carries
    #     meaning pyte consumes today (window title, hyperlink), so it goes
    #     through untouched. DCS/SOS/PM/APC are graphics and control strings
    #     pyte has NO branch for -- its parser falls through to draw(), so
    #     `ESC _Gf=100;a=T;QUFBQQ== ESC \` (kitty PNG) landed on the grid as the
    #     literal text `AGf=100;a=T;QUFBQQ==B`, and a sixel image as
    #     `Aq#0;2;100;0;0#1~~~B`. An agent driving yazi/chafa/viu read base64 as
    #     content, and `feed_errors` stayed 0 for both, so there was no
    #     diagnostic that could have noticed. They are therefore consumed HERE
    #     and emit nothing: the same "swallow it, draw nothing" a real terminal
    #     shows for a string it cannot interpret — and, like every other
    #     consume under the policy, COUNTED (once per string), so an image that
    #     the grid does not show is visible as an observation rather than as
    #     nothing at all.
    #   * a trailing ESC is held for one more byte: it may still start a string
    #     or a CSI. Nothing else is ever buffered.
    #   * MOUSE_RAW swallows the three raw bytes of an X10 report. That payload
    #     has no terminator to search for and can contain an ESC, so the fixed
    #     length is what ends it — and it is bounded by construction.
    _GROUND, _ESC_SEEN, _CSI, _STRING, _STRING_ESC, _DISCARD, _MOUSE_RAW = range(7)
    # Alias, not a second number: the cap IS the policy's cap, and a literal
    # here would let the two drift into disagreeing about what "bounded" means.
    _CSI_CAP = UNKNOWN_SEQUENCE_POLICY.cap

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._state = self._GROUND
        self._csi = bytearray()      # bytes after "ESC[" while a sequence is open
        # _string_bel is only ever True together with _string_emit: BEL is an
        # OSC terminator, and OSC is the one string family pyte understands.
        self._string_bel = False     # BEL ends this string, or only ST does
        self._string_emit = False    # forward this string's bytes to pyte, or not
        # Bytes still owed by an open X10 mouse report (never more than three).
        self._mouse_left = 0
        # The policy's observable. Counted, not swallowed, for the same reason
        # feed_errors exists: a screen that is quietly losing content must be
        # diagnosable from outside the process.
        self.unknown_sequences = 0
        self.last_unknown: str | None = None   # why, for the first one at least

    # The bytes-vs-str override is pyte's own Liskov violation, not ours:
    # Stream.feed takes str, ByteStream.feed narrows it to bytes and carries the
    # same ignore upstream. Matching it keeps this override honest to the class
    # we actually inherit from.
    def feed(self, data: bytes) -> None:  # type: ignore[override]
        # Fast path: with no escape in flight and none in this chunk there is
        # nothing to inspect, so the common bulk-output case skips the loop.
        if self._state == self._GROUND and b"\x1b" not in data:
            super().feed(data)
            return

        out = bytearray()
        i = 0
        n = len(data)
        state = self._state

        while i < n:
            if state == self._GROUND:
                j = data.find(b"\x1b", i)
                if j == -1:
                    out += data[i:]
                    break
                out += data[i:j]
                i = j + 1
                state = self._ESC_SEEN
                continue

            if state == self._ESC_SEEN:
                if i >= n:
                    break                       # hold a trailing ESC for one byte
                b = data[i]
                i += 1
                if b == 0x5B:                   # '['
                    self._csi.clear()
                    state = self._CSI
                elif b == 0x5D:                            # ']' OSC
                    out += b"\x1b]"                       # pyte consumes OSC: forward
                    self._string_bel = True                # BEL or ST terminates it
                    self._string_emit = True
                    state = self._STRING
                elif b in _CONTROL_STRING_INTRODUCERS:  # 'P' DCS 'X' SOS '^' PM '_' APC
                    # Counted HERE, at the introducer, because that is the
                    # only point at which the filter knows what it is
                    # consuming: the payload is never buffered (that is the
                    # rule), so a reason read from the introducer is the only
                    # one that cannot be a guess. It is still the fact an
                    # operator needs — a child emitted a graphics/control
                    # string, this module drew nothing, and the grid is
                    # missing an image. Silence here is the same defect the
                    # policy was written for: the reason this consume exists
                    # is that an agent must not silently lose content, and an
                    # image IS content to yazi/chafa/viu even when this
                    # module cannot render it. Once per STRING, not per byte
                    # and not per terminator, so one image is one observation
                    # however the PTY happened to chunk it.
                    self._reject(f"{_CONTROL_STRING_INTRODUCERS[b]} "
                                 f"graphics/control string payload consumed, "
                                 f"not drawn: {bytes((0x1B, b))!r} ... ST")
                    self._string_bel = False               # ST only (ECMA-48)
                    self._string_emit = False              # swallowed here, never drawn
                    state = self._STRING
                else:                           # two-byte escape / charset designator
                    out += b"\x1b" + bytes((b,))
                    state = self._GROUND
                continue

            if state == self._CSI:
                j = i
                while j < n and not 0x40 <= data[j] <= 0x7E:
                    j += 1
                if len(self._csi) + (j - i) > self._CSI_CAP:
                    self._csi.clear()           # abandon it; swallow to its final byte
                    # Counted like any other consumed sequence: an over-long
                    # parameter run is one we do not understand, and leaving it
                    # out would make the counter a worse description of what
                    # the screen is missing.
                    self._reject(f"CSI parameter run over the {self._CSI_CAP}-byte cap")
                    i = j
                    state = self._DISCARD
                    continue
                self._csi += data[i:j]
                i = j
                if i >= n:
                    break                       # hold the open sequence
                final = data[i]
                i += 1
                params = bytes(self._csi)
                self._csi.clear()
                if final == 0x4D and not params:              # 'M' with no count
                    # ESC[M is BOTH "X10 mouse report, three raw bytes follow"
                    # and "delete one line" (DL with its default count). The
                    # bytes cannot tell them apart, so the MODE decides, and
                    # the mode bytes may still be sitting in `out` rather than
                    # in pyte — flush first, or a report arriving in the same
                    # read as its own enable would be dispatched as a DL. Never
                    # guessed from the report itself: that is the whole point
                    # of tracking the mode.
                    if out:
                        self._state = state  # stay consistent if pyte raises
                        super().feed(bytes(out))
                        out.clear()
                    if self._mouse_reporting():
                        self._reject("X10 mouse report: ESC[M + 3 raw bytes")
                        self._mouse_left = 3
                        state = self._MOUSE_RAW
                        continue
                forwarded = self._disposition(params, final)
                if forwarded is not None:
                    out += forwarded
                state = self._GROUND
                continue

            if state == self._STRING:
                j = data.find(b"\x1b", i)
                if self._string_bel:
                    k = data.find(b"\x07", i)
                    if k != -1 and (j == -1 or k < j):
                        out += data[i:k + 1]
                        i = k + 1
                        state = self._GROUND
                        continue
                if j == -1:
                    if self._string_emit:
                        out += data[i:]         # stream the payload, never buffer it
                    break
                if self._string_emit:
                    out += data[i:j]
                i = j + 1
                state = self._STRING_ESC
                continue

            if state == self._STRING_ESC:
                if i >= n:
                    break                       # hold ESC: it may be an ST
                b = data[i]
                i += 1
                # ST is the ONLY terminator for these strings; the ESC of the
                # pair is held above across a read boundary. A bare 0x5C inside
                # a payload is NOT one -- it is a legal sixel data char
                # (0x3F + mask) and arbitrary binary in kitty RGB-direct, so
                # ending the string there would re-spill the rest as text.
                if b == 0x5C:                   # '\' -> ST
                    if self._string_emit:
                        out += b"\x1b\\"
                    state = self._GROUND
                else:                           # ESC inside the payload: stay in it
                    if self._string_emit:
                        out += b"\x1b" + bytes((b,))
                    state = self._STRING
                continue

            if state == self._MOUSE_RAW:
                # The X10 event payload: exactly three raw bytes, consumed
                # whatever they are. There is no terminator to search for and an
                # ESC inside them is a coordinate value, not a new sequence, so
                # the fixed length is what ends it — bounded by construction,
                # and the held remainder is at most three bytes.
                take = min(self._mouse_left, n - i)
                i += take
                self._mouse_left -= take
                if not self._mouse_left:
                    state = self._GROUND
                continue

            # state == self._DISCARD: drop bytes until the abandoned sequence ends
            j = i
            while j < n and not 0x40 <= data[j] <= 0x7E:
                j += 1
            if j >= n:
                i = n
                break                           # still inside the abandoned sequence
            i = j + 1                           # swallow it up to and including the final
            state = self._GROUND

        self._state = state
        if out:
            super().feed(bytes(out))

    def _reject(self, why: str) -> None:
        """Apply :data:`UNKNOWN_SEQUENCE_POLICY`: consume, count, say why.

        The only place the policy's observable is written, so "it swallows
        quietly" cannot come back for one family only. ``last_unknown`` keeps
        the FIRST reason rather than the latest: the first one is the one that
        explains a screen that started going wrong, and a stream of reports
        would otherwise overwrite it with the least interesting of them.
        """
        self.unknown_sequences += 1
        if self.last_unknown is None:
            self.last_unknown = why

    def _mouse_reporting(self) -> bool:
        """Is a mouse tracking mode set on the screen we are feeding?

        Read from ``Screen.mode`` through the same shift the mode registry uses
        (:data:`_PRIVATE_MODE_SHIFT`), because "the mouse is live" must not be
        a second, independent notion of that fact. This is the disambiguator
        for X10, whose introducer is byte-identical to delete-one-line.
        """
        mode = getattr(self.listener, "mode", ())
        return any(number << _PRIVATE_MODE_SHIFT in mode
                   for number in MOUSE_REPORTING_MODES)

    def _disposition(self, params: bytes, final: int) -> bytes | None:
        """The single place :data:`UNKNOWN_SEQUENCE_POLICY` is applied.

        ``params`` is the collected parameter byte run of one closed CSI
        (``ESC[`` already consumed) and ``final`` its final byte. Returns the
        bytes to forward to pyte, or ``None`` to consume the sequence whole —
        read to its end, drawn as nothing, counted, recovery continuing with
        the next byte.

        The cases, in the order they are decided:

        1. SGR with sub-parameters — rewritten when every group is something
           pyte can represent, dropped whole when none is (emitting ``ESC[m``
           instead would reset every attribute, which is worse than losing
           one). See :func:`_sgr_rewrite_params`.
        2. A parameter byte pyte cannot carry. pyte's parser ends the sequence
           AT such a byte and draws the remainder as text, so the sequence is
           not "a CSI with odd parameters", it is debris. This is the SGR 1006
           mouse report (``ESC[<b;x;yM``), the kitty keyboard protocol
           (``ESC[=1u``), and every other sequence built on a parameter byte
           pyte does not know.
        3. A final byte whose pyte handler was not written for this many
           parameters. pyte dispatches on the final byte alone, so this is the
           urxvt 1015 mouse report (``ESC[32;10;5M`` becomes three arguments to
           ``delete_lines`` and raises — and the raise is swallowed, losing
           every byte after it in that batch).
        4. The private form of a handler that does not accept one, same
           swallowed-raise path (``ESC[?6n``, DECXCPR).

        Anything else is forwarded untouched — including a final byte pyte has
        no entry for, which reaches ``Screen.debug``: a documented no-op, so it
        draws nothing, which is exactly what the policy asks for, and it keeps
        the sequence whole for a pyte that learns it later.
        """
        if final == 0x6D and b":" in params:                # 'm', sub-parameters
            rewritten = _sgr_rewrite_params(params)
            if rewritten is None:
                self._reject(f"SGR sub-parameters, all unknown: {params!r}")
                return None
            return b"\x1b[" + rewritten + b"m"

        if not _PYTE_CSI_PARAM_BYTES.issuperset(params):
            odd = bytes(b for b in params if b not in _PYTE_CSI_PARAM_BYTES)
            self._reject(f"CSI parameter byte {odd!r} pyte cannot carry: "
                         f"{params!r} + {bytes((final,))!r}")
            return None

        key = bytes((final,))
        # pyte turns the final byte into a parameter too, so an empty run is
        # still one argument: `ESC[H` is cursor_position(0), not ().
        count = params.count(b";") + 1
        private = b"?" in params
        arity = _CSI_MAX_PARAMS.get(key)
        if arity is not None:
            limit = arity[1] if private else arity[0]
            if limit >= 0 and count > limit:
                self._reject(f"{count} parameters into a {limit}-parameter "
                             f"pyte entry: {params!r} + {key!r}")
                return None
            if private and key not in _CSI_PRIVATE_OK:
                self._reject(f"private form of a handler without a private "
                             f"argument: {params!r} + {key!r}")
                return None
        return b"\x1b[" + params + key


class _Screen(pyte.Screen):
    """``pyte.Screen`` with measured real-terminal divergences addressed.

    **1. IL/DL keep the cursor column — a DELIBERATE CHOICE, not a bug fix.**
    ``pyte``'s ``insert_lines``/``delete_lines`` call ``carriage_return()``,
    snapping the cursor to column 0; this subclass keeps the column, so after
    ``ESC[5;8H ESC[1L abc`` we render ``"       abc"`` where pyte renders
    ``"abc"``.

    The implementations genuinely disagree, and the split is not what the
    original note here claimed. Counting what is documented:

        column 0 (pyte's behaviour)  : xterm, vte, and the DEC VT reference,
                                      which terminalguide gives as "Moves the
                                      cursor to the left margin"
        column kept (ours)          : tmux 3.6b, GNU screen, urxvt, konsole,
                                      linuxvc

    So five documented implementations keep the column and two reset it. The
    project's rule — match what two independent references agree on — points at
    keeping it, and tmux and GNU screen were both measured directly. That is why
    this stays.

    But it is a choice between real behaviours, NOT a defect in pyte, and the
    distinction matters: **this must never be upstreamed.** pyte's own docstrings
    cite VT102/VT220, whose reference says column 0, so a PR "fixing" it would
    move pyte away from the standard it targets and would rightly be rejected.
    That was caught by an independent re-check of a triage that had listed it as
    a mechanical upstream port; the earlier note in this docstring, claiming
    "real terminals keep the column" as though that were unanimous, is what made
    the mistake plausible.

    Well-behaved programs do not depend on the column after IL/DL, precisely
    because it varies — so the practical stakes are low either way. Originally
    surfaced by ``tests/_diff_fuzz_tmux.py``.

    **2. A zero-width joiner must not truncate the batch.**
    ``pyte.Screen.draw`` walks the batch character by character and, for a
    character that is neither width-1, width-2, nor a true combining mark, does
    ``else: break`` — abandoning **every remaining character in that batch**.
    Two extremely common codepoints land in that hole: VARIATION SELECTOR-16
    (U+FE0F, ``wcwidth`` 0, ``combining`` 0) and ZERO WIDTH JOINER (U+200D).

    So a program printing ``"MENU ♀️ Settings  Quit"`` in one write lost
    everything after the emoji: the agent perceived ``"MENU ♀"`` and would act
    on a menu whose other entries it could not see. Found by
    ``tests/_diff_tmux_pyte.py``, which diffs our grid against a real tmux pane
    — tmux keeps the whole line, so this was a genuine perception gap, not a
    representation difference.

    Fix: intercept those codepoints and append them to the previous cell's
    ``data``, exactly as pyte already does for combining marks, then let pyte
    draw the rest of the batch normally. The cursor does not advance (width 0),
    and a wide character's empty stub slot is stepped over so the mark attaches
    to the glyph itself. Controls (C0/C1, ESC) are never intercepted — the
    stream FSM must still see them.
    """

    # NOT changed: IL/DL when the cursor sits OUTSIDE a DECSTBM scroll region.
    # The generative fuzz flagged it, but the two reference emulators DISAGREE
    # with each other there: for `x ESC[8;9r ESC[2L`, tmux 3.6b performs the
    # insert (x shifts to row 2) while GNU screen discards it entirely. When
    # mature emulators diverge, the sequence is under-specified and there is no
    # ground truth to match — so we keep pyte's behaviour rather than picking a
    # side, and `_diff_fuzz_tmux.py` documents it as a known divergence. Real
    # TUIs do not drive IL from outside their own region.

    def index(self) -> None:
        """IND — line feed, but a cursor OUTSIDE the scroll region must not scroll it.

        pyte's ``index`` compares the cursor against the DECSTBM bottom margin
        and, on a match, scrolls the region. When the cursor is *below* the
        region entirely, that is wrong: the cursor should simply move down (or
        stay on the last row), leaving the region untouched. Measured on tmux
        3.6b: with region 3..6, text written at row 7 that autowraps continues on
        row 8, while pyte wrapped it back inside the region to row 5 — so
        anything a program painted below a scroll region (status bars, prompts
        under a pager) landed on the wrong rows for us. Found by
        ``tests/_diff_fuzz_tmux.py``.
        """
        top, bottom = self.margins or (0, self.lines - 1)
        if self.cursor.y > bottom:
            if self.cursor.y < self.lines - 1:
                self.cursor.y += 1
                self.dirty.add(self.cursor.y)
            return
        super().index()

    # xterm private modes that switch to the ALTERNATE screen buffer. pyte
    # implements none of them, so `ESC[?1049h` merely set an unknown mode bit and
    # a full-screen program (vim, less, htop — every TUI drive-tui exists to
    # drive) painted its alternate screen ON TOP of the main one. On exit the
    # main screen was never restored, so an agent read a merged, impossible
    # screen. Measured against tmux 3.6b, which follows xterm: 1049 saves the
    # cursor and clears the alternate buffer on entry and restores both on exit;
    # 1047/47 switch buffers without the cursor save.
    _ALT_MODES = (1049, 1047, 47)

    #: Private mode 1048 — save/restore the cursor as DECSC/DECRC do, WITHOUT
    #: switching buffers. It is the other half of 1049, which xterm documents as
    #: 1047 combined with 1048.
    #:
    #: EVIDENCE LEVEL, stated because it is weaker than everything else in this
    #: class: the xterm specification defines it, but NEITHER reference emulator
    #: implements it. Measured — a `1048h`/`1048l` pair does not restore the
    #: cursor in tmux 3.6b or GNU screen 4.00.03, while the same movement through
    #: DECSC/DECRC does in both (so the probe can detect a restore; the absence is
    #: real, not a rig artifact). Every full-screen program in practice emits 1049.
    #:
    #: Supported anyway because this layer's job is to perceive what a program
    #: SENT, and a program that sends 1048 means DECSC. The alternative — matching
    #: the references by ignoring it — would make us silently drop a documented
    #: sequence. Kept deliberately separate from _ALT_MODES so it can never affect
    #: buffer switching, and locked by a test that names the divergence.
    #:
    #: Note for whoever sees the behaviour change: once ``_PYTE_HAS_ALT`` is true
    #: this class hands 1048 to the base class, whose pending implementation uses
    #: a single dedicated slot rather than a stack — so repeated ``1048h`` will
    #: OVERWRITE rather than nest. Both are defensible (xterm says "as DECSC",
    #: and DECSC is a stack; a single slot cannot strand savepoints), neither
    #: reference emulator implements 1048 at all, so there is no ground truth to
    #: prefer one. Recorded here so the drift is not mistaken for a regression.
    _CURSOR_ONLY_MODE = 1048

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._alt_active = False
        self._saved_main: dict | None = None
        # (row, col, attrs). The pen travels with the position because 1049 is
        # defined as "save cursor as in DECSC", and DECSC saves the graphic
        # rendition too. Without it, a TUI that left reverse video or a colour
        # on made every character the shell wrote afterwards inherit it.
        self._saved_cursor: tuple[int, int, Char] | None = None
        # How many 1048 saves WE pushed onto pyte's savepoint stack, so an
        # unpaired 1048l cannot pop somebody else's savepoint or fall through
        # to restore_cursor's empty-stack homing.
        self._cursor_only_depth = 0

    def _enter_alt(self, save_cursor: bool) -> None:
        if self._alt_active:
            return
        self._saved_main = dict(self.buffer)
        self._saved_cursor = ((self.cursor.y, self.cursor.x, self.cursor.attrs)
                              if save_cursor else None)
        self.buffer.clear()
        self._alt_active = True
        # NOTE: the cursor is deliberately NOT homed. xterm clears the alternate
        # buffer but leaves the cursor where it was, and tmux 3.6b agrees:
        # `main\r\n` then ESC[?1049h then ALT puts ALT on row 1, not row 0.
        self.dirty.update(range(self.lines))

    def _leave_alt(self) -> None:
        if not self._alt_active:
            return
        self.buffer.clear()
        if self._saved_main is not None:
            self.buffer.update(self._saved_main)
        self._saved_main = None
        self._alt_active = False
        if self._saved_cursor is not None:
            y, x, attrs = self._saved_cursor
            # CLAMP. The screen may have been resized while the program owned
            # the alternate screen, and restoring a row that no longer exists
            # left the cursor permanently outside the buffer: every subsequent
            # write landed on a row `display` never renders, so the agent read a
            # screen that had silently stopped updating. Found by review after
            # the resize fix here clipped the saved BUFFER but not the saved
            # CURSOR — one half of the same defect.
            self.cursor.y = min(max(y, 0), self.lines - 1)
            self.cursor.x = min(max(x, 0), self.columns - 1)
            self.cursor.attrs = attrs
            self._saved_cursor = None
        self.dirty.update(range(self.lines))

    def reset(self) -> None:
        """Overloaded so RIS leaves the alternate screen.

        ``pyte.Screen.reset`` clears ``buffer`` but knows nothing about the
        alternate-screen state kept here, so after ``ESC c`` the flag stayed set:
        the next program's smcup was a silent no-op (it paints onto what the
        agent believes is the primary screen), and a later rmcup resurrected the
        pre-RIS screen. Real terminals return to the primary buffer on RIS.
        """
        super().reset()
        self._alt_active = False
        self._saved_main = None
        self._saved_cursor = None
        self._cursor_only_depth = 0

    def resize(self, lines: int | None = None,
               columns: int | None = None) -> None:
        """Resize, clipping the SAVED primary screen the same way as the live one.

        ``pyte.Screen.resize`` only touches ``self.buffer``, which during
        alternate-screen mode is the alternate buffer — the saved primary screen
        is invisible to it. So a terminal resized while a full-screen program was
        running (the user drags the window while ``vim``/``less``/``htop`` is up,
        or ``drive-tui``'s own ``resize`` action fires) restored a primary screen
        of the old shape on exit: the wrong ROWS, because pyte drops rows from
        the top while an untouched save keeps its original numbering, plus
        over-wide cells that `display` hides but a later grow-back would reveal.

        Found by re-auditing this class against the same defect in the upstream
        patch for pyte issue #90, where the offscreen buffer had the same hole.

        KNOWN DIVERGENCE, deliberately not "fixed". With DECSTBM margins set that
        exclude row 0, a shrink through the alternate screen restores different
        rows than the same shrink without one. The cause is in pyte: it shrinks by
        homing the cursor and calling ``delete_lines``, which does nothing when the
        cursor sits outside the scroll region, so the live buffer keeps its TOP rows
        (``AAA/BBB``) where the unmargined case keeps its bottom ones
        (``CCC/DDD``) — and with margins ``(1, 3)`` it keeps a single row.

        Matching that here was rejected rather than overlooked. Real terminals
        REFLOW on resize instead of clipping, and they reset DECSTBM as part of it
        — pyte itself calls ``set_margins()`` at the end of ``resize`` — so using
        the outgoing margins to decide which rows to drop has no counterpart to
        measure against. Copying an unverifiable rule into the second buffer would
        add a hacky buffer swap and would still not be right, only symmetric. This
        is the same call the project makes for IL/DL from outside a scroll region,
        where the two reference emulators disagree: record the divergence, do not
        pick a side. See tests/test_terminal_fidelity.py, which pins the
        no-margins case and documents this one without asserting on it.
        """
        old_lines, old_columns = self.lines, self.columns
        # `or` rather than `is None`: pyte's own resize does `lines = lines or
        # self.lines`, so 0 means "unchanged" there. Testing `is None` here made
        # resize(0, 0) — a no-op for the live screen — clip the saved primary
        # screen to nothing.
        new_lines = lines or old_lines
        new_columns = columns or old_columns
        super().resize(lines, columns)

        saved = self._saved_main
        if saved is None:
            return
        if new_lines < old_lines:
            # Match pyte: shrinking drops rows from the TOP, so the surviving
            # rows shift up and renumber. Reading low-to-high is safe because
            # the source index always leads the destination.
            drop = old_lines - new_lines
            for y in range(new_lines):
                row = saved.pop(y + drop, None)
                if row is not None:
                    saved[y] = row
                else:
                    saved.pop(y, None)
            for y in range(new_lines, old_lines):
                saved.pop(y, None)
        if new_columns < old_columns:
            for line in saved.values():
                for x in range(new_columns, old_columns):
                    line.pop(x, None)

    #: True when the installed ``pyte`` implements the alternate screen buffer
    #: itself, so this subclass must NOT switch as well.
    #:
    #: pyte has not implemented it in any release up to 0.8.2 (issue #90, open
    #: since 2017), which is why the implementation below exists. An upstream
    #: patch is pending, and the day it ships in a release every installation
    #: with the usual ``pyte>=0.8.1`` requirement picks it up automatically —
    #: at which point doing the work twice restores a BLANK primary screen on
    #: every full-screen program exit, i.e. exactly the bug this class was
    #: written to prevent, reintroduced silently by a dependency upgrade.
    #:
    #: Detected once at import rather than pinning ``pyte<0.8.3``: a version cap
    #: would keep users off the fix forever and has to be revised every release,
    #: whereas the capability check is correct both before and after, and needs
    #: no maintenance. When it reports True the base class does the switching and
    #: ``_alt_active`` simply mirrors ``screen.alternate_screen``.
    _PYTE_HAS_ALT: bool = hasattr(pyte.Screen, "alternate_screen")

    @property
    def alt_screen(self) -> bool:
        """True while the alternate screen buffer is active.

        Reads through to the base class where that implements the feature, so the
        answer is right whichever layer performed the switch.

        ``getattr`` rather than ``super().alternate_screen``. The default is
        unreachable for the reason it exists — ``_PYTE_HAS_ALT`` already proved the
        attribute is present — but NOT unconditionally, and the difference was
        pointed out by review rather than noticed here: ``hasattr`` on a *class*
        holding a ``@property`` is True without ever running the getter, so a future
        pyte whose getter itself raised ``AttributeError`` would be swallowed by the
        default and reported as ``False`` instead of surfacing. That is a narrow
        window (it needs an upstream getter bug, and any other exception type still
        propagates), and both candidate fallbacks are equally wrong in it —
        ``_alt_active`` is not maintained by this class once the base class owns the
        switching — so the behaviour stands and the limit is stated instead of
        being asserted away. It is written this way because the direct
        access needs a ``type: ignore[misc]`` on a pyte that lacks the attribute
        and NO ignore on a pyte that has it — so with ``warn_unused_ignores``, one
        spelling or the other fails the lint gate depending only on which pyte is
        installed. That is the same dependency-triggered break ``_PYTE_HAS_ALT``
        exists to prevent, and a version-dependent ignore would need revising on
        the very release that makes the capability check unnecessary. Verified
        clean under both stock 0.8.2 and a pyte carrying the attribute.
        """
        if self._PYTE_HAS_ALT:
            return bool(getattr(super(), "alternate_screen", False))
        return self._alt_active

    def set_mode(self, *modes: int, **kwargs) -> None:
        if kwargs.get("private"):
            if not self._PYTE_HAS_ALT:
                for mode in modes:
                    if mode in self._ALT_MODES:
                        self._enter_alt(save_cursor=(mode == 1049))
            # 1048 is cursor-only. Skipped when the base class implements it
            # itself, or the cursor would be saved twice.
            if self._CURSOR_ONLY_MODE in modes and not self._PYTE_HAS_ALT:
                self.save_cursor()
                self._cursor_only_depth += 1
        super().set_mode(*modes, **kwargs)

    def reset_mode(self, *modes: int, **kwargs) -> None:
        if kwargs.get("private"):
            if not self._PYTE_HAS_ALT:
                for mode in modes:
                    if mode in self._ALT_MODES:
                        self._leave_alt()
            # Only restore against a save WE made. pyte's restore_cursor homes
            # the cursor when its stack is empty (its documented DECRC
            # behaviour), so an unpaired `ESC[?1048l` — which both reference
            # emulators ignore outright — would otherwise teleport the cursor to
            # the top-left. The depth counter keeps DECSC's stack semantics for
            # repeated 1048h while making the unpaired case inert.
            if (self._CURSOR_ONLY_MODE in modes and not self._PYTE_HAS_ALT
                    and self._cursor_only_depth > 0):
                self._cursor_only_depth -= 1
                self.restore_cursor()
        super().reset_mode(*modes, **kwargs)

    def cursor_up(self, count: int | None = None) -> None:
        """CUU — a cursor already OUTSIDE the region is not clamped into it.

        pyte clamps to the DECSTBM top margin unconditionally, so a cursor below
        the region could not move above it. Real terminals only apply the margin
        clamp while the cursor is inside the region (measured on tmux 3.6b:
        region 9..10, cursor at row 2, ``ESC[2A`` reaches row 0; pyte pinned it
        at row 8). Found by ``tests/_diff_fuzz_tmux.py``.
        """
        top, bottom = self.margins or (0, self.lines - 1)
        if not (top <= self.cursor.y <= bottom):
            self.cursor.y = max(self.cursor.y - (count or 1), 0)
            return
        super().cursor_up(count)

    def cursor_down(self, count: int | None = None) -> None:
        """CUD — the mirror of :meth:`cursor_up`, and it was missed.

        ``pyte`` clamps to the DECSTBM bottom margin unconditionally
        (``min(cursor.y + count, bottom)``), so a cursor BELOW the region is
        dragged up into it — CUD moving the cursor UP. Measured on tmux 3.6b and
        GNU screen 4.00.03, which agree: region 3..6, cursor on row 8, ``ESC[1B``
        lands on row 9; pyte and this class both landed on row 6.

        Found by an independent review that asked why ``index`` and ``cursor_up``
        were overridden here but their mirror was not — the same defect class,
        already fixed twice, left in place a third time because nothing tested it.
        """
        top, bottom = self.margins or (0, self.lines - 1)
        if not (top <= self.cursor.y <= bottom):
            self.cursor.y = min(self.cursor.y + (count or 1), self.lines - 1)
            return
        super().cursor_down(count)

    def next_line(self) -> None:
        """NEL (``ESC E``) — index AND carriage return, unconditionally.

        pyte routes ``ESC E`` to ``linefeed``, which only returns to column 0
        when LNM is set; NEL is defined to always do both. So ``ESC[2;5H ESC E``
        left us writing at column 4 where tmux 3.6b writes at column 0. Found by
        ``tests/_diff_fuzz_tmux.py``. (Registered below via the stream's escape
        map so the dispatch actually reaches this method.)
        """
        self.index()
        self.carriage_return()

    def delete_characters(self, count: int | None = None) -> None:
        """DCH — deleting a two-column glyph must remove BOTH of its cells.

        pyte deletes one cell per requested count without regard to width, so
        deleting a wide character left its stub behind as a stray blank and every
        following column shifted by one (measured: ``中x`` + CR + ``ESC[1P``
        gives ``"x"`` on tmux 3.6b, we produced ``" x"``). Found by
        ``tests/_diff_fuzz_tmux.py``.
        """
        if _PYTE_DCH_HANDLES_WIDE:
            # The installed pyte already widens the count itself; adding to it
            # would delete one cell too many. See _pyte_dch_handles_wide.
            super().delete_characters(count)
            return
        line = self.buffer[self.cursor.y]
        x = self.cursor.x
        extra = 0
        if x < self.columns:
            cur = line[x].data
            if cur and (wcwidth_cached(cur[0]) == 2
                        or (len(cur) > 1 and "️" in cur)):
                extra = 1  # its stub travels with it
        super().delete_characters((count or 1) + extra)

    def _shift_lines(self, start: int, bottom: int, count: int, down: bool) -> None:
        """Move whole rows within [start, bottom], filling the vacated ones.

        pyte's own IL walks the range popping source rows after copying them,
        which for ``count > 1`` leaves rows *missing* from its sparse buffer
        rather than present-and-blank. A later DL then renumbered around those
        holes and deleted the wrong row: ``ESC[3L Q ESC[1M`` left ``Q`` on screen
        for us where tmux 3.6b and GNU screen both end up blank. Rebuilding the
        affected span explicitly keeps every row present, so row indices stay
        meaningful. Found by ``tests/_diff_fuzz_tmux.py``.
        """
        span = list(range(start, bottom + 1))
        rows = [self.buffer.get(y) for y in span]
        if down:
            moved = [None] * count + rows[:-count] if count <= len(rows) else [None] * len(rows)
        else:
            moved = rows[count:] + [None] * count if count <= len(rows) else [None] * len(rows)
        for y, row in zip(span, moved):
            if row is None:
                self.buffer.pop(y, None)
                # Touch the row so it exists as a real blank line, not a hole.
                self.buffer[y]  # defaultdict factory materialises it
            else:
                self.buffer[y] = row
        self.dirty.update(span)

    def insert_lines(self, count: int | None = None) -> None:
        top, bottom = self.margins or (0, self.lines - 1)
        if top <= self.cursor.y <= bottom:
            self._shift_lines(self.cursor.y, bottom, min(count or 1,
                                                         bottom - self.cursor.y + 1),
                              down=True)
            return
        col = self.cursor.x
        super().insert_lines(count)
        self.cursor.x = col  # real terminals keep the column; pyte homes it

    def delete_lines(self, count: int | None = None) -> None:
        """DL — deleting must BLANK the rows it vacates, not leave them behind.

        ``insert_lines`` above already routes through :meth:`_shift_lines` to keep
        every row present in pyte's sparse buffer. DL had the mirror-image hole and
        did not: pyte copies ``buffer[y] = buffer.pop(y + count)`` only ``if
        y + count in self.buffer``, so when the source row was never written the
        DESTINATION keeps its old contents instead of going blank.

        Two visible consequences, both measured against tmux 3.6b AND GNU screen
        4.00.03, which agree on all of them: ``Q`` + CR + ``ESC[1M`` left ``Q`` on
        screen where both references clear it, and ``A/B/C`` + ``ESC[2M`` deleted
        only ONE row, leaving ``['C', 'B']`` where both give ``['C']``.

        The earlier IL-side fix masked this: the repro recorded for it happened to
        materialise the rows first, so it passed while the minimal case stayed
        broken. Found by triaging which of this project's fixes are genuinely
        absent upstream.
        """
        top, bottom = self.margins or (0, self.lines - 1)
        if top <= self.cursor.y <= bottom:
            self._shift_lines(self.cursor.y, bottom,
                              min(count or 1, bottom - self.cursor.y + 1),
                              down=False)
            return
        col = self.cursor.x
        super().delete_lines(count)
        self.cursor.x = col

    def _clear_split_wide(self) -> None:
        """Blank a two-column glyph the cursor is about to half-overwrite.

        Writing into either half of a wide character must destroy the WHOLE
        glyph — a terminal cannot show half of it. Real terminals blank both
        cells: after ``中`` + ``ESC[1D`` + ``X``, tmux 3.6b and GNU screen both
        render ``" X"``. pyte instead left the wide char in place and dropped the
        new character entirely, so we rendered ``"中"`` — the write vanished, and
        an agent reading that row saw stale text with nothing reporting a
        problem. Found by ``tests/_diff_fuzz_tmux.py``.
        """
        line = self.buffer[self.cursor.y]
        x = self.cursor.x
        if x >= self.columns:
            return
        blank = self.cursor.attrs._replace(data=" ")
        # Cursor sits on the stub half: blank the base to our left too.
        if line[x].data == "" and x - 1 >= 0:
            line[x - 1] = blank
            line[x] = blank
            self.dirty.add(self.cursor.y)
            return
        # Cursor sits on the base half of a wide glyph: blank its stub as well.
        cur = line[x].data
        if cur and (wcwidth_cached(cur[0]) == 2 or (len(cur) > 1 and "️" in cur)):
            line[x] = blank
            if x + 1 < self.columns and line[x + 1].data == "":
                line[x + 1] = blank
            self.dirty.add(self.cursor.y)

    def _clear_orphan_stub(self) -> None:
        """Blank a stub cell whose wide base was just overwritten.

        Drawing a two-column glyph over the BASE of an existing one leaves the
        old glyph's stub stranded one cell further right: it still reads as the
        empty-string continuation of a character that no longer exists, so every
        column after it renders one place off. Real terminals blank it.

        Concretely: with ``│││♀️♀️♀️`` on screen, writing ``中文中文`` from column
        0 put ``文``'s stub on the first emoji's base and left that emoji's own
        stub behind, so we rendered ``中文中文││ ▄`` where tmux 3.6b and GNU
        screen (which agree here) render ``中文中文││▄▄``. Found by
        ``tests/_diff_fuzz_tmux.py`` — it took a VS16 cluster plus a DECSTBM
        change plus two ICH rounds to expose, which is exactly the kind of
        accumulation hand-written cases never reach.
        """
        x = self.cursor.x
        if 0 < x < self.columns:
            line = self.buffer[self.cursor.y]
            if line[x].data == "" and line[x - 1].data not in ("", None):
                prev = line[x - 1].data
                if not (wcwidth_cached(prev[0]) == 2
                        or (len(prev) > 1 and "️" in prev)):
                    line[x] = self.cursor.attrs._replace(data=" ")
                    self.dirty.add(self.cursor.y)

    def draw(self, data: str) -> None:
        from wcwidth import wcwidth  # pyte's own width dependency

        pending: list[str] = []
        for char in data:
            code = ord(char)
            is_control = code < 0x20 or 0x80 <= code <= 0x9F
            if (not is_control and wcwidth(char) == 0
                    and unicodedata.combining(char) == 0):
                if pending:
                    super().draw("".join(pending))
                    pending = []
                line = self.buffer[self.cursor.y]
                idx = self.cursor.x - 1
                if idx >= 0 and line[idx].data == "":
                    idx -= 1  # step over the stub slot of a wide character
                if idx >= 0:
                    prev = line[idx]
                    line[idx] = prev._replace(data=prev.data + char)
                    self.dirty.add(self.cursor.y)
                    if char == "️" and wcwidth(prev.data[:1]) == 1:
                        # VARIATION SELECTOR-16 requests EMOJI presentation, which
                        # real terminals render two cells wide even when wcwidth
                        # reports 1 for the base character (measured: tmux 3.6b and
                        # GNU screen both advance 2 for U+2640 U+FE0F). Claim the
                        # stub cell and advance so every following column matches
                        # the real terminal — otherwise one emoji shifts the whole
                        # rest of the line by one.
                        if self.cursor.x < self.columns:
                            line[self.cursor.x] = \
                                self.cursor.attrs._replace(data="")
                            self.cursor.x = min(self.cursor.x + 1, self.columns)
                continue
            if pending:
                super().draw("".join(pending))
                pending = []
            # A two-column glyph that cannot fit before the right margin wraps
            # WHOLE to the next line; pyte squeezes it into the last cell.
            # Measured on tmux 3.6b: an emoji written at column 40 of a 40-col
            # screen appears on the next row, not split across the margin.
            if (wcwidth(char) == 2 and self.cursor.x == self.columns - 1
                    and mo.DECAWM in self.mode):
                self.carriage_return()
                self.linefeed()
            # A write that lands on half of a wide glyph must destroy all of it.
            self._clear_split_wide()
            super().draw(char)
            self._clear_orphan_stub()
        if pending:
            super().draw("".join(pending))


def safe_screen_display(screen: pyte.Screen) -> list[str]:
    """Crash-safe mirror of ``pyte.Screen.display``.

    pyte's own ``display`` renderer calls ``wcwidth(char[0])`` unconditionally,
    which raises ``IndexError`` when a cell's ``data`` is the empty string — a
    state reachable from malformed byte runs (a wide char followed by CR and an
    invalid UTF-8 tail). This mirrors pyte's renderer exactly (including the
    wide-char stub skip) but renders an empty cell as a single blank instead of
    crashing. Byte-identical to ``pyte.Screen.display`` on well-formed screens
    (verified). Shared by :class:`ScreenModel` and the screenshot tooling.
    """
    from wcwidth import wcwidth  # pyte's own width dependency

    def render_row(line) -> str:
        out: list[str] = []
        is_wide = False
        for x in range(screen.columns):
            if is_wide:
                is_wide = False
                continue
            char = line[x].data
            if not char:  # the guard pyte lacks: empty cell -> single blank
                out.append(" ")
                is_wide = False
                continue
            # Skip the stub slot for anything occupying two columns. pyte checks
            # only ``char[0]``, which misses an emoji-presentation cluster like
            # U+2640 U+FE0F: its base is wcwidth 1, yet real terminals advance
            # two columns (measured on tmux 3.6b and GNU screen), and _Screen.draw
            # reserves the stub accordingly. Without this, the stub renders as an
            # extra blank and every following column is off by one.
            is_wide = wcwidth(char[0]) == 2 or (len(char) > 1 and "️" in char)
            out.append(char)
        return "".join(out)

    return [render_row(screen.buffer[y]) for y in range(screen.lines)]


class CellAttrs(NamedTuple):
    """Reduced view of a single :class:`pyte.screens.Char`."""

    data: str
    fg: str
    bg: str
    bold: bool
    reverse: bool


class ScreenModel:
    """Feed PTY bytes into a ``pyte`` screen and read structured state back out."""

    def __init__(self, cols: int = 80, rows: int = 24) -> None:
        self._cols = cols
        self._rows = rows
        self.screen = _Screen(cols, rows)
        # ByteStream decodes UTF-8 incrementally, so multibyte chars split across
        # feed() boundaries are reassembled correctly.
        self.stream = _ByteStream(self.screen)
        # Count of feed() batches pyte failed to parse (malformed control seqs).
        # Observable so a SYSTEMIC failure (e.g. a regression that makes every
        # feed raise) is not silently indistinguishable from the occasional
        # garbled byte run it is meant to tolerate.
        self.feed_errors = 0
        # Per-row visual_hash CRCs (see visual_hash): polling recomputed every
        # cell of every row 33x/second even when nothing had changed.
        self._visual_row_crcs: list[int | None] = []
        # Device-query replies (DSR-CPR "ESC[6n", DA "ESC[c") that pyte generates
        # while parsing. pyte routes them to Screen.write_process_input, which is a
        # no-op by default — so a program that SYNCHRONOUSLY waits for a cursor-
        # position report can stall/degrade because nothing answers. We capture
        # them here (pyte builds the correct reply from its own cursor/attrs) and
        # PtySession.pump() writes them back to the PTY. See drain_replies().
        self._reply_buf = bytearray()
        # Deliberate instance-level replacement of a base-class no-op: this is
        # pyte's documented hook for device-query replies, and it is a method on
        # Screen rather than a callback attribute, so there is no non-assigning
        # way to install it.
        self.screen.write_process_input = self._collect_reply  # type: ignore[method-assign]

    def _collect_reply(self, data) -> None:
        """pyte hands us the bytes/str it wants sent back to the process."""
        if isinstance(data, str):
            data = data.encode("utf-8", "replace")
        self._reply_buf.extend(data)

    def stream_incomplete(self) -> bool | None:
        """Is the byte-to-text path holding an unfinished sequence? (A04-S2p)

        Read-only diagnostic. Two independent places can be mid-sequence: this
        project's streaming SGR filter (a partially received CSI) and pyte's own
        incremental UTF-8 decoder (a multi-byte character split across reads).
        ``True`` means "do not call this observation complete"; ``False`` means
        both are at a clean boundary.

        ``None`` is returned when the decoder cannot be inspected at all: a
        missing answer must never be reported as a confident ``False``, because
        a caller treating "no buffered bytes" as "the screen is current" is the
        exact mistake this exists to prevent.
        """
        state = getattr(self.stream, "_state", None)
        ground = getattr(type(self.stream), "_GROUND", None)
        decoder = getattr(self.stream, "utf8_decoder", None)
        if state is None or ground is None or decoder is None:
            return None
        if state != ground:
            return True                       # a CSI/string is still open in the filter
        try:
            buffered, _flags = decoder.getstate()
        except Exception:
            return None
        return bool(buffered)

    def drain_replies(self) -> bytes:
        """Return and clear any pending device-query replies pyte generated.

        PtySession.pump() calls this after feed() and writes the result back to
        the PTY, so DSR-CPR / DA queries from the driven program get answered.
        """
        if not self._reply_buf:
            return b""
        out = bytes(self._reply_buf)
        self._reply_buf.clear()
        return out

    # -- the reject-don't-guess observable ----------------------------------
    @property
    def unknown_sequences(self) -> int:
        """How many control sequences :data:`UNKNOWN_SEQUENCE_POLICY` consumed.

        Distinct from :attr:`feed_errors`, and the distinction is the point.
        ``feed_errors`` counts batches pyte could not parse at all; this counts
        sequences we understood well enough to know we do NOT understand, and
        deliberately drew nothing for: rejected CSI sequences, consumed X10
        mouse reports, and consumed DCS/SOS/PM/APC strings. All three were 0
        through every one of the defects this policy was written for, because
        pyte "parsed" all of them — so a screen that had gained debris and lost
        content looked healthy from the outside. Non-zero is a statement that
        the grid is missing something the program drew, not that this module
        is broken.

        A DCS or APC payload is counted here because this IS the consume the
        policy describes — read to its end, emitted to pyte as nothing — and
        leaving it out made the counter a worse description of the grid for
        exactly the family an image-drawing program uses. It is not a claim
        that this module failed: it is the statement that the child drew an
        image (yazi, chafa, viu, timg) that is not in the snapshot.
        """
        return getattr(self.stream, UNKNOWN_SEQUENCE_POLICY.counter, 0)

    @property
    def last_unknown(self) -> str | None:
        """Why the first sequence was consumed, or ``None`` if none was.

        The counterpart to the counter: a bare number says that something was
        dropped, this says what. One string, bounded by
        :data:`UNKNOWN_SEQUENCE_POLICY` because a rejected parameter run is at
        most the cap long.
        """
        return getattr(self.stream, "last_unknown", None)

    # -- feeding -----------------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Feed raw bytes from the PTY into the screen. Safe with partial data.

        Hardened against malformed control sequences: some byte sequences make
        ``pyte`` itself raise (e.g. a CSI insert/delete op with an empty leading
        numeric parameter — ``ESC[;@`` — dispatches to ``insert_characters`` with
        the wrong arity → ``TypeError``). pyte already resets its own parser FSM
        before re-raising (streams.py ``_send_to_parser``), so the stream stays
        usable; we swallow the exception here so one hostile/garbled byte run from
        a real program cannot break perception. Bytes up to the offending control
        char are already drawn; the rest of that batch is dropped, and the next
        ``feed`` continues normally. Verified: valid sequences are unaffected.
        """
        if data:
            try:
                self.stream.feed(data)
            except Exception:
                # pyte has already re-initialised its parser (streams.py
                # _send_to_parser), so the stream stays usable; keep going. Bump
                # an observable counter rather than swallowing silently, so a
                # systemic failure is diagnosable instead of a frozen screen.
                self.feed_errors += 1

    def resize(self, cols: int, rows: int) -> None:
        """Resize the underlying screen. Keep this in sync with the PTY winsize."""
        self._cols = cols
        self._rows = rows
        # pyte.Screen.resize takes (lines, columns).
        self.screen.resize(rows, cols)

    # -- geometry ----------------------------------------------------------

    @property
    def cols(self) -> int:
        return self.screen.columns

    @property
    def rows(self) -> int:
        return self.screen.lines

    # -- terminal modes -----------------------------------------------------

    def mode(self, name: Mode | str) -> bool:
        """Is terminal mode ``name`` set right now?

        ``name`` is a :class:`Mode` member or its string value, so a caller can
        ask without importing anything: ``model.mode("alt_screen")``. An
        unknown name raises ``ValueError`` — the set is closed, and a typo must
        not read as "that mode is off", which is the failure this replaces.
        Those used to be reachable only by hand: ``app_cursor`` and
        ``alt_screen`` were the two properties that existed, each with its own
        private decoding of where pyte keeps the answer, and there was no way to
        ask about DECAWM, DECOM, DECSCNM, IRM or LNM at all even though pyte
        branches on every one of them while parsing.

        Strict on purpose: an unreadable screen propagates rather than
        answering ``False``. The two callers on the driving hot path keep their
        own guards (:attr:`app_cursor`), so this does not change what they see.
        """
        return MODE_REGISTRY[Mode(name)].resolve(self.screen)

    def modes(self) -> frozenset[Mode]:
        """Every mode currently set, as a frozenset of :class:`Mode` members.

        The complement of :meth:`mode` for callers that want the whole state at
        once (an agent deciding how to interpret the screen, or a snapshot
        carrying it). Never raises for an unknown name — the set is closed by
        construction, so there is nothing to miss.
        """
        return frozenset(m for m in MODE_REGISTRY if MODE_REGISTRY[m].resolve(self.screen))

    @property
    def app_cursor(self) -> bool:
        """True when the program has enabled DECCKM (application cursor keys).

        A full-screen / curses program that has called ``keypad(True)`` puts the
        terminal in DECCKM (``ESC[?1h``); pyte records this as private mode 1 in
        ``screen.mode`` (the value ``32``). In that state the app expects SS3
        cursor sequences (``ESC O A``) — sending CSI (``ESC [ A``) moves nothing.
        :meth:`session.PtySession.send_keys` reads this to pick the right form.

        Now :meth:`mode(Mode.APP_CURSOR)`. The shift pyte applies to private
        modes lives in :data:`MODE_REGISTRY` instead of inline here, and the
        ``try`` stays: this is read on every key send, where an unreadable
        screen must degrade to "send CSI" rather than raise into the driver.
        """
        try:
            return self.mode(Mode.APP_CURSOR)
        except Exception:
            return False

    @property
    def mouse_report(self) -> MouseReport:
        """What the program has asked for about the mouse, from the MODE.

        Not a :class:`Mode` member on purpose — see the note above
        :data:`MOUSE_REPORTING_MODES` — but the same storage and the same
        private-mode shift, so it is not a second notion of "the mouse is on".

        It exists because the reports themselves are consumed and discarded
        (:data:`UNKNOWN_SEQUENCE_POLICY`). A click is therefore invisible on
        the grid, and an agent that assumed every pixel of the screen came from
        the program would be wrong the moment a human or a script clicked.
        ``enabled`` is the honest answer to "can that happen right now".

        ``cells`` is the half that must not be guessed: under 1016 the very
        same bytes mean PIXELS, so reading them as cell indices points at a row
        that does not exist. ``None`` means refuse.
        """
        return _mouse_report(self.screen)

    # -- plain text --------------------------------------------------------

    @property
    def display(self) -> list[str]:
        """List of rendered lines (wide-char aware, right-padded to ``cols``).

        Fast path is ``pyte.Screen.display``. But pyte's renderer does
        ``wcwidth(char[0])`` unconditionally, which raises ``IndexError`` when a
        cell's ``data`` is the empty string — a state reachable from certain
        malformed byte runs (wide char + CR + invalid UTF-8 tail). One such cell
        would otherwise blind every ``display``/``snapshot``/``to_text`` call
        until it happened to be overwritten. We fall back to a crash-safe
        per-cell render (byte-identical to pyte on well-formed screens; verified)
        that treats an empty cell as a blank.
        """
        try:
            return list(self.screen.display)
        except Exception:
            return safe_screen_display(self.screen)

    def text(self) -> str:
        """The full screen joined with newlines (trailing padding preserved).

        Goes through the hardened :attr:`display` (not ``screen.display``) so a
        malformed empty-data cell can never crash text extraction — which also
        protects ``content_hash`` and the readiness stability loop that build on
        it.
        """
        return "\n".join(self.display)

    # -- cursor ------------------------------------------------------------

    @property
    def cursor(self) -> tuple[int, int]:
        """Cursor as ``(row, col)``, both 0-based."""
        return (self.screen.cursor.y, self.screen.cursor.x)

    @property
    def cursor_hidden(self) -> bool:
        return not self.mode(Mode.CURSOR_VISIBLE)

    @property
    def alt_screen(self) -> bool:
        """True while a full-screen program owns the screen.

        The single most useful fact about a screen after "what does it say": a
        driving agent decides differently when ``vim``/``less``/``htop`` is up
        than at a shell prompt — whether ``q`` quits or types a letter, whether
        arrow keys navigate or edit. It was previously reachable only as
        ``model.screen.alt_screen``, i.e. by reaching through to the pyte object.

        The buffer state is asked through :meth:`mode` now, but still resolves
        to :attr:`_Screen.alt_screen` — pyte sets a bit for 1047 and never clears
        it, so the bit set cannot answer "which buffer is live" on its own.
        """
        return self.mode(Mode.ALT_SCREEN)

    @property
    def title(self) -> str:
        return self.screen.title or ""

    @property
    def base_reverse(self) -> bool:
        """Screen-wide reverse baseline (DECSCNM). Highlight is measured vs this."""
        return self.mode(Mode.REVERSE_VIDEO)

    # -- attributes --------------------------------------------------------

    def cell(self, row: int, col: int) -> CellAttrs:
        """Return attributes for one cell.

        Safe against the sparse buffer: ``screen.buffer`` is a real ``defaultdict``
        (indexing a missing *row* would insert it), so we only index rows within
        range; missing *cells* fall back to the screen default char without
        mutating anything.
        """
        if not (0 <= row < self.screen.lines and 0 <= col < self.screen.columns):
            dc = self.screen.default_char
            return CellAttrs(dc.data, dc.fg, dc.bg, dc.bold, dc.reverse)
        ch = self.screen.buffer[row][col]  # StaticDefaultDict: missing col -> default
        return CellAttrs(ch.data, ch.fg, ch.bg, ch.bold, ch.reverse)

    def row_cells(self, row: int) -> list[CellAttrs]:
        """Return the attribute cells for a whole row, left to right."""
        if not (0 <= row < self.screen.lines):
            return []
        buf = self.screen.buffer[row]
        out = []
        for col in range(self.screen.columns):
            ch = buf[col]
            out.append(CellAttrs(ch.data, ch.fg, ch.bg, ch.bold, ch.reverse))
        return out

    # -- stability ---------------------------------------------------------

    def content_hash(self) -> int:
        """CRC32 of the plain-text display.

        Excludes cursor position and all attributes, so cursor movement and
        attribute-only churn (blink/reverse cycling) do not count as changes for
        stability detection.
        """
        return zlib.crc32(self.text().encode("utf-8", "replace"))

    def visual_hash(self) -> int:
        """CRC32 of visible cells, their attributes, and the cursor state.

        Unlike :meth:`content_hash`, this changes when a TUI moves a selection
        using reverse video/background color or only moves the cursor. It is a
        separate primitive so text-only stability detection keeps ignoring blink
        and cosmetic attribute churn.

        INCREMENTAL: ``wait_visual_change`` polls this every 30 ms, and hashing
        every cell of every row cost 16.6 ms on a 300x100 screen — 55% of the
        polling budget, spent almost entirely on rows that had not changed. We
        keep a per-row CRC and recompute only the rows ``pyte`` marks dirty
        (``Screen.dirty``, which nothing else in this codebase consumes, so we
        may drain it). The returned value is identical to the exhaustive
        computation — ``tests/test_perf_contract.py`` asserts that equivalence
        against a from-scratch model as well as the timing ceilings.
        """
        rows = self.screen.lines
        columns = self.screen.columns
        buffer = self.screen.buffer
        row_crcs = self._visual_row_crcs
        if len(row_crcs) != rows:  # first call, or a resize
            row_crcs = self._visual_row_crcs = [None] * rows
            todo: list[int] = list(range(rows))
        else:
            todo = [y for y in self.screen.dirty if 0 <= y < rows]
            todo.extend(y for y in range(rows) if row_crcs[y] is None)
        for row in todo:
            line = buffer[row]
            parts = []
            for col in range(columns):
                char = line[col]
                parts.append(
                    f"{char.data}\x00{char.fg}\x00{char.bg}\x00"
                    f"{char.bold:d}{char.italics:d}{char.underscore:d}"
                    f"{char.strikethrough:d}{char.reverse:d}{char.blink:d}"
                )
            row_crcs[row] = zlib.crc32("\x01".join(parts).encode("utf-8", "replace"))
        self.screen.dirty.clear()
        crc = 0
        for row_crc in row_crcs:
            crc = zlib.crc32((row_crc or 0).to_bytes(4, "big"), crc)
        cursor_state = (self.screen.cursor.y, self.screen.cursor.x, self.cursor_hidden)
        return zlib.crc32(repr(cursor_state).encode("ascii"), crc)


