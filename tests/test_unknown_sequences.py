#!/usr/bin/env python3
"""A control sequence the perception chain does not understand is REJECTED, not guessed at.

One policy, stated once in ``smartcli_core/screen_model.py`` as
``UNKNOWN_SEQUENCE_POLICY`` and applied in exactly one place,
``_ByteStream._disposition``. This file is its evidence.

The policy, restated here so a reader does not have to open the source to know
what is being claimed:

* a sequence we do not understand is read to its end, emitted to pyte as
  NOTHING, counted in ``ScreenModel.unknown_sequences``, and recovery continues
  with the next byte;
* it is never drawn as text — control debris on the grid is indistinguishable
  from content an agent is supposed to read;
* it is never handed to a pyte entry point that was not written for its shape —
  pyte dispatches on the FINAL BYTE alone, so the wrong shape raises inside
  pyte, ``ScreenModel.feed`` swallows the raise, and the REST OF THAT OUTPUT
  BATCH IS DROPPED. Silent content loss is worse than a dropped sequence;
* it never wedges the stream: the open-sequence cap and the
  swallow-to-final-byte recovery still apply, so a program emitting garbage
  cannot cost the driver its screen.

It is deliberately NOT an unbounded swallowing machine: an unrecognised final
byte is still forwarded (pyte routes it to ``Screen.debug``, a documented
no-op, which draws nothing and keeps the sequence whole).

The three concrete defects this generalises, all reproduced against pyte 0.8.2
before the fix and each covered below:

* SGR 1006 mouse report ``ESC[<0;10;5M``  -> the literal text ``0;10;5M`` on
  the grid, no error signal. pyte's parser ends the sequence AT the ``<``.
* urxvt 1015 mouse report ``ESC[32;10;5M``  -> three arguments into
  ``delete_lines(count)``, so pyte raises, and everything after it in that
  batch is lost. Silent, and a *loss* rather than a corruption.
* X10 mouse report ``ESC[M`` + three raw bytes -> dispatched to ``delete_lines``,
  genuinely mutating the screen, and the three raw bytes drawn as text.

Reachable with no SmartCLI code involved: run a child under tmux, have a human
click, and tmux forwards the click back as ordinary PTY output.

Pure memory: no PTY, no process, no subprocess. Run:
    python tests/test_unknown_sequences.py
"""
from __future__ import annotations

import argparse
import inspect
from pathlib import Path
import random
import sys
import unittest

ap = argparse.ArgumentParser(add_help=False)
ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
args, rest = ap.parse_known_args()
sys.dont_write_bytecode = True
sys.path.insert(0, str(args.repo.resolve()))
try:
    from smartcli_core.screen_model import (
        MODE_REGISTRY,
        MOUSE_REPORTING_MODES,
        UNKNOWN_SEQUENCE_POLICY,
        Mode,
        ScreenModel,
        _CSI_MAX_PARAMS,
        _CSI_PRIVATE_OK,
        _PYTE_CSI_PARAM_BYTES,
        _ByteStream,
        _mouse_report,
    )
except ModuleNotFoundError as exc:
    print(f"NOT_RUN: {exc}", file=sys.stderr)
    raise SystemExit(2)

import pyte  # noqa: E402  — after sys.path, so this is the project's pyte

ST = b"\x1b\\"


# --- the reproducers, with text on both sides ------------------------------
# The assertion that matters is "AB", not "B": a filter that eats one byte too
# many on the way out of a swallowed sequence also produces a clean-looking B.
SGR_PRESS = b"A\x1b[<0;10;5MB"
SGR_RELEASE = b"A\x1b[<0;10;5mB"
SGR_MODIFIERS = b"A\x1b[<32;10;5MB"          # 32: ctrl/shift held
URXVT_PRESS = b"A\x1b[32;10;5MB"
URXVT_MOTION = b"A\x1b[64;10;5MB"            # 64: motion, button 0

# X10: the introducer is byte-identical to delete-one-line, so it is only a
# report when a mouse mode is actually on — see X10NeedsTheMode.
X10_ON = b"\x1b[?1000h"
X10_REPORT = b"A\x1b[M\x20\x2b\x25B"          # payload " +%": printable on purpose
# A payload whose FIRST byte is ESC. X10 encodes a coordinate as byte+32, so
# 0x1B is a legal value; a filter that mistakes it for a new sequence swallows
# the following real sequence instead, and the "B" never turns red.
X10_ESC = b"A\x1b[M\x1b[0\x1b[31mB"


def fed(*payloads: bytes, cols: int = 30, rows: int = 4, **pre) -> ScreenModel:
    """One model, fed each payload in turn (a session, in order)."""
    m = ScreenModel(cols=cols, rows=rows)
    for payload in payloads:
        m.feed(payload)
    return m


def state(model: ScreenModel):
    """Everything a disposition could plausibly change, not just row 0."""
    return (tuple(model.display), model.cursor, model.content_hash(),
            tuple(sorted(model.screen.mode)), model.feed_errors,
            model.unknown_sequences, model.last_unknown)


def row0(model: ScreenModel) -> str:
    return model.display[0].rstrip()


class MouseReportsNeverReachPyte(unittest.TestCase):
    """Every report encoding, and the text on both sides of it."""

    def assert_untouched(self, *pre: bytes, payload: bytes) -> None:
        m = fed(*pre, payload)
        self.assertEqual(row0(m), "AB",
                         f"{payload!r} corrupted the grid: {row0(m)!r}")
        self.assertEqual(m.feed_errors, 0, "pyte raised on a mouse report")
        self.assertEqual(m.cursor, (0, 2), "the report moved the cursor")
        self.assertEqual(m.unknown_sequences, 1,
                         "a consumed sequence must be observable, not silent")

    def test_sgr_1006_press_and_release(self):
        self.assert_untouched(payload=SGR_PRESS)
        self.assert_untouched(payload=SGR_RELEASE)

    def test_sgr_1006_with_modifier_flags(self):
        # SGR carries modifiers in the first field; more groups must not make
        # the report look like something else.
        self.assert_untouched(payload=SGR_MODIFIERS)

    def test_urxvt_1015_press_and_motion(self):
        self.assert_untouched(payload=URXVT_PRESS)
        self.assert_untouched(payload=URXVT_MOTION)

    def test_x10_is_consumed_when_a_mouse_mode_is_on(self):
        self.assert_untouched(X10_ON, payload=X10_REPORT)

    def test_x10_payload_containing_esc_is_data(self):
        # 0x1B is a legal X10 coordinate byte (value+32). Reading it as a new
        # sequence would swallow the red-SGR that follows, and "B" would stay
        # default-coloured — which is the assertion that discriminates.
        m = fed(X10_ON, X10_ESC)
        self.assertEqual(row0(m), "AB")
        self.assertEqual(m.screen.buffer[0][1].fg, "red",
                         "the ESC inside the report payload was read as a "
                         "sequence introducer, and the real one was lost")
        self.assertEqual(m.unknown_sequences, 1)

    def test_every_report_shape_together_still_leaves_the_text(self):
        # Each reproducer is "A<report>B", so three of them in a row must read
        # back as "ABABAB" — the grid proves each report was consumed rather
        # than drawn, and the tail proves the filter re-synced.
        m = fed(X10_ON, SGR_PRESS, URXVT_MOTION, X10_REPORT, b"tail")
        self.assertEqual(row0(m), "ABABABtail")
        self.assertEqual(m.feed_errors, 0)
        self.assertEqual(m.unknown_sequences, 3)

    def test_reports_are_not_drawn_anywhere_on_the_grid(self):
        m = fed(X10_ON, SGR_PRESS, URXVT_PRESS)
        joined = "\n".join(m.display)
        for debris in ("0;10;5", "32;10;5", "64;10;5", "+%"):
            self.assertNotIn(debris, joined,
                             f"mouse report debris {debris!r} reached the grid")

    def test_a_report_does_not_mutate_the_screen(self):
        # urxvt 1015 is the one that used to be a LOSS: pyte raised, and
        # everything after it in that batch vanished. "AB" is the whole claim.
        m = fed(b"first line\r\nsecond line\r\n", b"third",
                URXVT_PRESS, b"fourth")
        self.assertEqual(m.display[0].rstrip(), "first line")
        self.assertEqual(m.display[1].rstrip(), "second line")
        self.assertEqual(m.display[2].rstrip(), "thirdABfourth")

    def test_every_split_point_is_safe(self):
        for payload in (SGR_PRESS, SGR_RELEASE, URXVT_PRESS, URXVT_MOTION):
            expected = state(fed(X10_ON, payload))
            for cut in range(1, len(payload)):
                with self.subTest(cut=cut, payload=payload):
                    self.assertEqual(state(fed(X10_ON, payload[:cut], payload[cut:])),
                                     expected)
            with self.subTest(payload=payload, chunking="bytewise"):
                self.assertEqual(
                    state(fed(X10_ON, *[payload[i:i + 1] for i in range(len(payload))])),
                    expected)
            rnd = random.Random(20261001)
            for _ in range(20):
                cuts = sorted(rnd.sample(range(1, len(payload)),
                                         min(5, len(payload) - 1)))
                chunks = [payload[a:b] for a, b in zip([0] + cuts, cuts + [None])]
                with self.subTest(payload=payload, cuts=cuts):
                    self.assertEqual(state(fed(X10_ON, *chunks)), expected)


class X10NeedsTheMode(unittest.TestCase):
    """``ESC[M`` is two different commands. The MODE decides which, never the bytes.

    This is the case that makes "reject what you do not understand" a policy
    rather than a reflex: blindly consuming ``ESC[M`` + 3 bytes would break
    delete-one-line for every program that never enabled a mouse, and blindly
    forwarding it would keep dispatching a click as a scroll.
    """

    def test_without_a_mouse_mode_esc_m_is_still_delete_one_line(self):
        m = fed(b"A\r\nB", b"\x1b[1;1H", b"\x1b[M", b"X")
        self.assertEqual(m.display[0].rstrip(), "X")
        self.assertEqual(m.display[1].rstrip(), "")
        self.assertEqual(m.unknown_sequences, 0,
                         "a plain DL must not be reported as unknown")

    def test_with_a_mouse_mode_the_same_bytes_are_a_report(self):
        m = fed(b"A\r\nB", b"\x1b[?1000h", b"\x1b[1;1H", b"\x1b[M", b"\x20\x2b\x25")
        self.assertEqual(m.display[0].rstrip(), "A")
        self.assertEqual(m.display[1].rstrip(), "B",
                         "the report was dispatched as delete-one-line")
        self.assertEqual(m.unknown_sequences, 1)

    def test_the_mode_in_the_same_read_as_the_report_is_honoured(self):
        # The filter batches: a report and the ESC[?1000h that enables it can
        # land in one read, and the mode bytes are not in pyte yet. Deciding
        # before flushing would read the report as a DL and draw its payload.
        m = fed(b"A\r\nB\x1b[?1000h\x1b[1;1H\x1b[M\x20\x2b\x25")
        self.assertEqual(m.display[0].rstrip(), "A")
        self.assertEqual(m.display[1].rstrip(), "B")
        self.assertEqual(m.unknown_sequences, 1)

    def test_every_tracking_mode_turns_x10_into_a_report(self):
        for number in (9, 1000, 1002, 1003):
            with self.subTest(mode=number):
                m = fed(b"A\r\nB", b"\x1b[?%dh" % number, b"\x1b[1;1H",
                        b"\x1b[M\x20\x2b\x25")
                self.assertEqual(m.display[1].rstrip(), "B")
                self.assertEqual(m.unknown_sequences, 1)

    def test_a_half_arrived_report_is_not_a_complete_observation(self):
        m = fed(X10_ON, b"A\x1b[M\x20\x2b")
        self.assertEqual(row0(m), "A")
        self.assertTrue(m.stream_incomplete(),
                        "two bytes of a three-byte report are still buffered")
        m.feed(b"\x25B")
        self.assertEqual(row0(m), "AB")
        self.assertFalse(m.stream_incomplete())

    def test_a_never_finished_report_cannot_buffer_without_bound(self):
        m = fed(X10_ON, b"A\x1b[M")
        for _ in range(64):
            m.feed(b"\x20" * 1024)
        self.assertEqual(m.unknown_sequences, 1,
                         "bytes were spilled out of a fixed-length report")
        self.assertLessEqual(getattr(m.stream, "_mouse_left", 0), 3)


class WindowTitleLookalikeIsNotAReport(unittest.TestCase):
    """A report-shaped byte run inside a string belongs to the application.

    The reason the filter is a streaming state machine and not a buffer regex:
    a whole-chunk regex cannot tell ``ESC[<0;10;5M`` the introducer from the
    same bytes inside a window title, and getting it wrong silently eats the
    user's title.
    """

    def test_bell_terminated_title(self):
        m = fed(b"\x1b]0;title \x1b[<0;10;5M end\x07AFTER")
        self.assertEqual(m.title, "title \x1b[<0;10;5M end")
        self.assertEqual(row0(m), "AFTER")
        self.assertEqual(m.unknown_sequences, 0)

    def test_st_terminated_title(self):
        m = fed(b"\x1b]2;\x1b[32;10;5M" + ST + b"AFTER")
        self.assertEqual(m.title, "\x1b[32;10;5M")
        self.assertEqual(row0(m), "AFTER")
        self.assertEqual(m.unknown_sequences, 0)

    def test_x10_lookalike_inside_a_dcs_payload(self):
        m = fed(b"\x1b_Gf=100;a=T;\x1b[M\x20\x2b\x25" + ST + b"AFTER")
        self.assertEqual(row0(m), "AFTER")
        self.assertEqual(m.unknown_sequences, 0)


class ThePolicyItself(unittest.TestCase):
    """The rule is named, its data is honest, and it is applied where it says."""

    def test_the_policy_forbids_exactly_the_two_things(self):
        self.assertFalse(UNKNOWN_SEQUENCE_POLICY.draws_unknown_bytes_as_text)
        self.assertFalse(UNKNOWN_SEQUENCE_POLICY.forwards_to_unmatched_pyte_entry)

    def test_the_cap_is_the_cap_the_filter_uses(self):
        # Two literals for one number would let "bounded" mean two things.
        from smartcli_core.screen_model import _ByteStream
        self.assertEqual(_ByteStream._CSI_CAP, UNKNOWN_SEQUENCE_POLICY.cap)
        self.assertGreater(UNKNOWN_SEQUENCE_POLICY.cap, 0)

    def test_the_counter_name_is_the_attribute_the_model_reads(self):
        self.assertEqual(UNKNOWN_SEQUENCE_POLICY.counter, "unknown_sequences")
        m = fed(b"A\x1b[<0;10;5MB")
        self.assertEqual(m.unknown_sequences,
                         getattr(m.stream, UNKNOWN_SEQUENCE_POLICY.counter))

    def test_an_unknown_sequence_is_counted_and_explained(self):
        m = fed(b"A\x1b[<0;10;5MB")
        self.assertEqual(m.unknown_sequences, 1)
        self.assertIsNotNone(m.last_unknown)
        self.assertIn("cannot carry", m.last_unknown)
        m2 = fed(b"")            # a clean screen says nothing, not "0 reasons"
        self.assertEqual(m2.unknown_sequences, 0)
        self.assertIsNone(m2.last_unknown)

    def test_a_clean_stream_is_silent(self):
        # The counter only means something if it stays at 0 for good input.
        m = fed(b"\x1b[2J\x1b[H", b"plain", b"\x1b[1;31mred\x1b[0m",
                b"\x1b[38;2;255;0;128mX", b"\x1b[4:3mY", b"\x1b[3;7r",
                b"\x1b[5;8HZ", b"\x1b[2P\x1b[1L\x1b[1M", b"\x1b[?1049h\x1b[?1049l",
                b"\x1b]0;title\x07", b"\x1b[?1h\x1b[?25l")
        self.assertEqual(m.unknown_sequences, 0, m.last_unknown)
        self.assertIsNone(m.last_unknown)
        self.assertEqual(m.feed_errors, 0)

    def test_it_is_not_an_unbounded_swallowing_machine(self):
        # An unrecognised FINAL byte is still forwarded: pyte has no entry and
        # routes it to Screen.debug, a documented no-op, which draws nothing.
        # Refusing to forward would be a policy that only ever grows.
        m = fed(b"A\x1b[1;2~B")          # unknown final '~'
        self.assertEqual(row0(m), "AB")
        self.assertEqual(m.unknown_sequences, 0)
        m2 = fed(b"A\x1b[>cB")            # secondary DA: '>' is a param pyte skips
        self.assertEqual(row0(m2), "AB")
        self.assertEqual(m2.unknown_sequences, 0)

    def test_a_known_final_with_too_many_parameters_is_rejected(self):
        # The urxvt case, named as a shape rather than as a protocol: three
        # parameters cannot be delete_lines(count).
        m = fed(b"A\x1b[1;2;3MB")
        self.assertEqual(row0(m), "AB")
        self.assertEqual(m.unknown_sequences, 1)
        self.assertIn("parameters into", m.last_unknown)

    def test_the_private_form_of_a_handler_without_one_is_rejected(self):
        # ESC[?6n is DECXCPR, a query real programs send. pyte's parser calls
        # report_device_status(6, private=True) and the call raises.
        m = fed(b"A\x1b[?6nB")
        self.assertEqual(row0(m), "AB")
        self.assertEqual(m.feed_errors, 0, "the old shape lost the whole batch")
        self.assertEqual(m.unknown_sequences, 1)
        self.assertIn("private form", m.last_unknown)

    def test_the_arity_table_matches_the_installed_pyte(self):
        # The whole point of the table is that it describes pyte's handlers as
        # pyte CALLS them: positionally for a plain CSI, positionally plus
        # private= for a DEC private one. If a handler's arity changes, this
        # must fail rather than let the filter mis-join silently. Bound
        # methods, so `self` is not counted as a parameter pyte would supply.
        screen = pyte.Screen(20, 4)
        for final, handler in pyte.Stream.csi.items():
            key = final.encode()
            with self.subTest(final=final, handler=handler):
                self.assertIn(key, _CSI_MAX_PARAMS,
                              f"no arity recorded for CSI {final!r}")
                params = inspect.signature(getattr(screen, handler)).parameters
                positional = [p for p in params.values()
                              if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
                variadic = any(p.kind is p.VAR_POSITIONAL for p in params.values())
                plain = -1 if variadic else len(positional)
                # pyte passes private= by keyword, so a declared `private`
                # parameter is one slot pyte's own call never fills positionally.
                dec = -1 if variadic else len([p for p in positional
                                               if p.name != "private"])
                self.assertEqual(_CSI_MAX_PARAMS[key], (plain, dec))
        self.assertEqual({k.decode() for k in _CSI_MAX_PARAMS},
                         set(pyte.Stream.csi),
                         "the arity table has a final pyte does not dispatch")

    def test_the_private_ok_set_matches_the_handlers_that_accept_one(self):
        screen = pyte.Screen(20, 4)
        for final, handler in pyte.Stream.csi.items():
            key = final.encode()
            params = inspect.signature(getattr(screen, handler)).parameters
            accepts = ("private" in params
                       or any(p.kind is p.VAR_KEYWORD for p in params.values()))
            with self.subTest(final=final, handler=handler):
                self.assertEqual(key in _CSI_PRIVATE_OK, accepts)
        # A handler with no entry in the arity table is one pyte routes to
        # Screen.debug(**kwargs), which accepts the private form, so the two
        # sets have to stay subsets of the dispatch table to stay comparable.
        self.assertTrue(_CSI_PRIVATE_OK <= set(_CSI_MAX_PARAMS))

    def test_the_param_alphabet_is_what_pyte_can_carry(self):
        # pyte's loop ends a CSI at the first byte it does not absorb, so the
        # accepted set is digits, ';', '?', and the two it explicitly skips.
        self.assertEqual(_PYTE_CSI_PARAM_BYTES,
                         frozenset(b"0123456789;? >"))
        for bad in (b"<", b"=", b":", b"!", b"@", b"/"):
            with self.subTest(byte=bad):
                self.assertNotIn(bad, _PYTE_CSI_PARAM_BYTES)

    def test_every_expressible_mouse_mode_is_registered(self):
        # 2004 reports focus, not the mouse; counting it would report a live
        # mouse for a program that only asked about focus.
        self.assertEqual(set(MOUSE_REPORTING_MODES), {9, 1000, 1002, 1003,
                                                      1005, 1006, 1015, 1016})
        self.assertNotIn(2004, MOUSE_REPORTING_MODES)


class UnknownSequencesStayRecoverable(unittest.TestCase):
    """Consumed, not absorbed: the stream keeps working afterwards."""

    def test_an_over_long_sequence_is_still_bounded_by_the_cap(self):
        m = fed(b"\x1b[" + b"9" * (UNKNOWN_SEQUENCE_POLICY.cap * 4))
        self.assertEqual(row0(m), "")
        self.assertLessEqual(len(m.stream._csi), UNKNOWN_SEQUENCE_POLICY.cap)
        # An abandoned run is a sequence we did not understand, so it counts
        # like any other: leaving it out would make the counter a worse
        # description of what the grid is missing.
        self.assertEqual(m.unknown_sequences, 1)
        self.assertIn("cap", m.last_unknown)
        m.feed(b"OK")
        self.assertEqual(row0(m), "K",
                         "the abandoned sequence still owns its final byte")
        m.feed(b"\x1b[4:3mZ")
        self.assertEqual(row0(m), "KZ")
        self.assertTrue(m.screen.buffer[0][1].underscore)

    def test_the_next_sequences_after_a_rejection_still_work(self):
        m = fed(SGR_PRESS, b"\x1b[4:3mX")
        self.assertEqual(row0(m), "ABX")
        self.assertTrue(m.screen.buffer[0][2].underscore,
                        "the filter lost sync after a consumed sequence")
        m.feed(b"\x1b[2;5HZ")
        self.assertEqual(m.display[1][4], "Z")

    def test_a_rejection_does_not_wedge_a_partly_open_sequence(self):
        m = fed(b"A\x1b[<0;10;5")            # the report is not closed yet
        self.assertEqual(row0(m), "A")
        self.assertTrue(m.stream_incomplete())
        m.feed(b"MB")
        self.assertEqual(row0(m), "AB")
        self.assertFalse(m.stream_incomplete())

    def test_a_run_of_rejections_is_bounded_and_then_recovers(self):
        m = fed(b"head")
        for _ in range(200):
            m.feed(b"\x1b[<0;1;1M\x1b[32;1;1M")
        m.feed(b"tail")
        self.assertEqual(row0(m), "headtail")
        self.assertEqual(m.unknown_sequences, 400)
        self.assertEqual(m.feed_errors, 0)


class MouseModeQuery(unittest.TestCase):
    """An agent must be able to ask whether the mouse is live, and in what unit."""

    def test_off_by_default(self):
        r = fed().mouse_report
        self.assertFalse(r.enabled)
        self.assertEqual(r.modes, ())
        self.assertIsNone(r.cells)

    def test_every_registered_mode_is_reported(self):
        for number in MOUSE_REPORTING_MODES:
            with self.subTest(mode=number):
                r = fed(b"\x1b[?%dh" % number).mouse_report
                self.assertTrue(r.enabled)
                self.assertEqual(r.modes, (number,))

    def test_modes_are_stored_the_way_pyte_stores_them(self):
        # Derive the private-mode shift from the registry rather than trusting a
        # literal, so this fails if the shift is ever wrong — and read the bit
        # off a stock screen, so the query cannot be reading its own shadow.
        spec = MODE_REGISTRY[Mode.APP_CURSOR]
        factor = spec.bit // spec.numbers[0]
        self.assertEqual(factor, 1 << 5,
                         "pyte stores private modes shifted left by five")
        m = fed(b"\x1b[?1006h")
        self.assertIn(1006 * factor, m.screen.mode)
        self.assertTrue(m.mouse_report.enabled)

    def test_sgr_1006_reports_cells(self):
        self.assertIs(fed(b"\x1b[?1000h\x1b[?1006h").mouse_report.cells, True)

    def test_sgr_1016_reports_pixels(self):
        # Byte-identical reports; the unit is the only difference, and reading
        # pixels as cells points at a row that does not exist.
        r = fed(b"\x1b[?1016h").mouse_report
        self.assertTrue(r.enabled)
        self.assertIs(r.cells, False)

    def test_1006_and_1016_together_refuse_rather_than_guess(self):
        r = fed(b"\x1b[?1006h\x1b[?1016h").mouse_report
        self.assertTrue(r.enabled)
        self.assertIsNone(r.cells, "an unknowable unit must not be resolved")

    def test_reset_turns_it_off_again(self):
        for number in MOUSE_REPORTING_MODES:
            with self.subTest(mode=number):
                m = fed(b"\x1b[?%dh" % number, b"\x1b[?%dl" % number)
                self.assertFalse(m.mouse_report.enabled)
                self.assertEqual(m.mouse_report.modes, ())

    def test_focus_reporting_is_not_mouse_reporting(self):
        self.assertFalse(fed(b"\x1b[?2004h").mouse_report.enabled)

    def test_the_query_reads_only_modes_and_disturbs_nothing(self):
        m = fed(b"\x1b[?1000h\x1b[?1006h", b"hello")
        before = (m.content_hash(), m.cursor, tuple(m.display),
                  tuple(sorted(m.screen.mode)))
        seen = {(r.enabled, r.modes, r.cells) for r in
                [m.mouse_report for _ in range(3)]}
        self.assertEqual(seen, {(True, (1000, 1006), True)},
                         "the query must be stable, not just side-effect free")
        self.assertEqual(before, (m.content_hash(), m.cursor, tuple(m.display),
                                  tuple(sorted(m.screen.mode))))

    def test_mouse_is_not_reachable_through_the_closed_mode_enum(self):
        # The closed set is a single-bit contract with two documented
        # exceptions; mouse reporting is nine numbers with no single bit, so
        # adding it there would need a third probe. Assert the consequence
        # rather than the preference, so the next person to "just add it as a
        # Mode" meets a failure instead of a comment.
        m = fed(b"\x1b[?1006h")
        self.assertTrue(m.mouse_report.enabled)
        self.assertNotIn("mouse_report", {member.value for member in Mode})
        with self.assertRaises(ValueError):
            m.mode("mouse_report")
        with self.assertRaises(ValueError):
            m.mode("mouse_reporting")
        # And nothing in the closed set claims the mouse is on, so an agent
        # reading only modes() cannot mistake the two for one answer.
        self.assertFalse(m.modes() & {member for member in Mode
                                      if "mouse" in member.value})

    def test_a_stock_pyte_screen_answers_the_mouse_query_too(self):
        from smartcli_core.screen_model import _mouse_report
        self.assertEqual(_mouse_report(pyte.Screen(20, 4)),
                         fed().mouse_report)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0], *rest])
