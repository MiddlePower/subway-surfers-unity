#!/usr/bin/env python3
"""Regression tests for the original Unity 2019/Emscripten dynCall wrappers.

Run: py -m unittest discover -s tools -p "test_*.py"
Tests use *only user-provided diagnostic bytes*, not the commercial build.
"""
import unittest
from resolve_dyncall_methods import candidate_dyncall_indirections


class DynCallDecoderTests(unittest.TestCase):
    def assert_decodes(self, raw_hex, mask, base, type_index):
        # A WebAssembly function body begins with a local declaration count.
        body = bytes.fromhex('00 ' + raw_hex)
        candidates = candidate_dyncall_indirections(body, 0, 0, [(0, len(body))])
        self.assertEqual(len(candidates), 1, candidates)
        got_mask, got_base, table_idx, got_type, _ = candidates[0]
        self.assertEqual((got_mask, got_base, table_idx, got_type),
                         (mask, base, 0, type_index))

    def test_coin_collected_wrapper(self):
        self.assert_decodes(
            '20 01 20 02 20 03 20 04 20 00 41 ff 3f 71 41 a9 f6 06 6a 11 08 00 0b',
            0x1FFF, 113449, 8
        )

    def test_coin_event_wrapper(self):
        self.assert_decodes(
            '20 01 20 02 20 00 41 ff ff 00 71 41 93 f3 04 6a 11 04 00 0b',
            0x3FFF, 80275, 4
        )

    def test_pickup_wrapper(self):
        self.assert_decodes(
            '20 01 20 02 20 03 20 00 41 ff ff 00 71 41 96 f5 05 6a 11 09 00 0b',
            0x3FFF, 96918, 9
        )

    def test_no_mask_with_offset(self):
        self.assert_decodes('20 00 41 05 6a 11 02 00 0b', 0xFFFFFFFF, 5, 2)


if __name__ == '__main__':
    unittest.main()
