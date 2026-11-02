#!/usr/bin/env python3
"""Synthetic tests for the safe local Unity->browser event bridge."""
import unittest

from challenge_wasm_bridge import (
    COIN_MARKER, HOVERBOARD_MARKER, JS_BRIDGE_NAME, JS_ORIGINAL,
    bridge_import, marker_instruction, runtime_bridge, uleb_i32,
)
from patch_no_coin_local import uleb
from resolve_wasm_methods import Reader, analyze


def name(s):
    b = s.encode("utf-8")
    return uleb(len(b)) + b


def section(number, payload):
    return bytes([number]) + uleb(len(payload)) + payload


def minimal_wasm():
    # One void(i32) type, two imported functions. The intended bridge is
    # the SECOND function, to test correct import index counting.
    types = section(1, b"\x01\x60\x01\x7f\x00")
    imports = (
        b"\x02" +
        name("env") + name("unrelated") + b"\x00\x00" +
        name("env") + name(JS_BRIDGE_NAME) + b"\x00\x00"
    )
    return b"\0asm\x01\0\0\0" + types + section(2, imports)


class BridgeTests(unittest.TestCase):
    def test_find_import_by_name_and_signature(self):
        wasm = minimal_wasm()
        types, type_ids, imported, *rest = analyze(wasm)
        self.assertEqual(imported, 2)
        self.assertEqual(bridge_import(wasm, types, type_ids, imported), 1)

    def test_markers_are_i32_and_calls_have_expected_index(self):
        for marker in (COIN_MARKER, HOVERBOARD_MARKER):
            code = marker_instruction(1, marker)
            self.assertEqual(code[0], 0x41)
            r = Reader(code, 1)
            self.assertEqual(r.sint(), marker)
            self.assertEqual(r.byte(), 0x10)
            self.assertEqual(r.uint(), 1)
            self.assertEqual(r.pos, len(code))
            self.assertLess(marker, 2**31)

    def test_generated_js_dispatches_only_reserved_signals(self):
        source = "prefix" + JS_ORIGINAL + "suffix"
        modified = runtime_bridge(source)
        self.assertIn("runner-game-event", modified)
        self.assertIn(str(COIN_MARKER), modified)
        self.assertIn(str(HOVERBOARD_MARKER), modified)
        self.assertEqual(modified.count("function _JS_Eval_EvalJS"), 1)
        self.assertIn("suffix", modified)

    def test_refuse_unknown_runtime(self):
        with self.assertRaises(RuntimeError):
            runtime_bridge("function _JS_Eval_EvalJS(ptr) { eval(ptr) }")


if __name__ == "__main__":
    unittest.main()
