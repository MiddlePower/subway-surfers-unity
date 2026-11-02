#!/usr/bin/env python3
"""Unit tests for the local WASM function-body patcher, using synthetic code only."""
import unittest

from resolve_wasm_methods import analyze, Reader
from patch_no_coin_local import uleb, replace_function_body, build_call_die_body


def wasm_section(number, contents):
    return bytes([number]) + uleb(len(contents)) + contents


class NoCoinWasmPatchTests(unittest.TestCase):
    def setUp(self):
        # An artificial module with two functions:
        # 0: void (i32, i32, i32, i32); 1: void (i32, i32).
        ty_coin = bytes([0x60, 0x04, 0x7F, 0x7F, 0x7F, 0x7F, 0x00])
        ty_die = bytes([0x60, 0x02, 0x7F, 0x7F, 0x00])
        self.wasm = (
            b'\x00asm\x01\x00\x00\x00'
            + wasm_section(1, b'\x02' + ty_coin + ty_die)
            + wasm_section(3, b'\x02\x00\x01')
            + wasm_section(10, b'\x02\x02\x00\x0b\x02\x00\x0b')
        )

    def test_patch_preserves_function_types(self):
        body = build_call_die_body(1)
        patched, previous = replace_function_body(self.wasm, 0, 0, body)
        self.assertEqual(previous, b'\x00\x0b')
        types, functions, imports, _, bodies, _ = analyze(patched)
        self.assertEqual(imports, 0)
        self.assertEqual(len(functions), 2)
        self.assertEqual(len(bodies), 2)
        self.assertEqual(types[functions[0]], (b'\x7f' * 4, b''))
        self.assertEqual(types[functions[1]], (b'\x7f' * 2, b''))
        first_pos, first_length = bodies[0]
        self.assertEqual(patched[first_pos:first_pos + first_length], body)

    def test_patching_does_not_mutate_original(self):
        source = self.wasm
        replace_function_body(source, 0, 0, build_call_die_body(1))
        self.assertEqual(source, self.wasm)

    def test_cannot_patch_imported_function(self):
        with self.assertRaises(ValueError):
            replace_function_body(self.wasm, 0, 1, build_call_die_body(1))


if __name__ == '__main__':
    unittest.main()
