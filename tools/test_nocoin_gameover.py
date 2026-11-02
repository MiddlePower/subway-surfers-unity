#!/usr/bin/env python3
"""Unit tests for the local-only game-over test patch (synthetic WASM)."""
import unittest

from patch_no_coin_local import replace_function_body
from resolve_wasm_methods import analyze
from try_nocoin_gameover import build_die_via_game_instance


def uleb(value):
    out = bytearray()
    while True:
        b = value & 127
        value >>= 7
        out.append(b | (128 if value else 0))
        if not value:
            return bytes(out)


def section(kind, body):
    return bytes([kind]) + uleb(len(body)) + body


class NoCoinGameOverTests(unittest.TestCase):
    def setUp(self):
        # Synthetic module with three functions:
        # 0: Coin.Pickup -> void(i32, i32)
        # 1: Game.get_Instance -> i32(i32)
        # 2: Game.Die -> void(i32, i32)
        pickup = b'\x60\x02\x7f\x7f\x00'
        get_game = b'\x60\x01\x7f\x01\x7f'
        die = b'\x60\x02\x7f\x7f\x00'
        self.module = (b'\0asm\x01\0\0\0'
                       + section(1, b'\x03' + pickup + get_game + die)
                       + section(3, b'\x03\x00\x01\x02')
                       + section(10, b'\x03\x02\x00\x0b\x02\x00\x0b\x02\x00\x0b'))

    def test_replacement_calls_get_instance_then_die(self):
        body = build_die_via_game_instance(1, 2)
        self.assertEqual(body, bytes.fromhex('00 41 00 10 01 41 00 10 02 0b'))
        new_module, old_body = replace_function_body(self.module, 0, 0, body)
        self.assertEqual(old_body, b'\0\x0b')
        types, funcs, imports, _, bodies, _ = analyze(new_module)
        self.assertEqual(len(funcs), 3)
        self.assertEqual(len(bodies), 3)
        self.assertEqual((types[funcs[0]], types[funcs[1]], types[funcs[2]]),
                         ((b'\x7f\x7f', b''), (b'\x7f', b'\x7f'), (b'\x7f\x7f', b'')))
        at, size = bodies[0]
        self.assertEqual(new_module[at:at+size], body)

    def test_large_function_indices_use_leb128(self):
        body = build_die_via_game_instance(200, 44566)
        self.assertTrue(body.startswith(b'\x00\x41\x00\x10'))
        self.assertEqual(body[-1], 0x0b)
        self.assertGreater(len(body), 10)


if __name__ == '__main__':
    unittest.main()
