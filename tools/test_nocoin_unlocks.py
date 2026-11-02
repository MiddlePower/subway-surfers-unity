#!/usr/bin/env python3
"""Synthetic unit tests for the private No-Coin inventory experiment."""
import unittest

from resolve_wasm_methods import Reader
from try_nocoin_unlocks import (
    MAX_ITEMS, build_inventory_preamble, enum_ids, find_records, exact_record,
    output_page_for,
    prepend_to_existing_body, signed_leb, verify_parameter_types,
    verify_upgrade_ids,
)

MOCK_METADATA = """// Namespace: Info
public enum UpgradeType // TypeDefIndex: 10
{
    // Fields
    public const UpgradeType hoverboard = 1;
    public const UpgradeType headstart2000 = 3;
    public const UpgradeType scorebooster = 15;
}
// Namespace: Characters
public enum CharacterId // TypeDefIndex: 11
{
    public const CharacterId _None = -1;
    public const CharacterId Jake = 0;
    public const CharacterId Tricky = 1;
    public const CharacterId Fresh = 2;
}
// Namespace: Boards
public enum BoardId // TypeDefIndex: 12
{
    public const BoardId _invalid = -1;
    public const BoardId OldSkool = 2;
    public const BoardId Something = 3;
}
// Namespace: Data.Save
public class InventorySave : DataManager<InventorySave> // TypeDefIndex: 13
{
    // Methods
    public static int get_keys() { }
    public static void SetKeys(int newAmount) { }
    public static int GetAmount(UpgradeType powerup) { }
    public static void IncreaseAmount(UpgradeType powerup, int quantity) { }
}
// Namespace: Data.Managers
public static class CharacterManager // TypeDefIndex: 16
{
    // Methods
    public static bool IsCharacterOwned(Characters.CharacterId characterId) { }
    public static void UnlockCharacter(Characters.CharacterId characterId) { }
}
// Namespace: Data.Managers
public static class BoardManager // TypeDefIndex: 17
{
    // Methods
    public static bool IsBoardOwned(Boards.BoardId boardId) { }
    public static void UnlockBoard(Boards.BoardId boardId) { }
}
// Namespace: SYBO.Subway
public class Game : MonoBehaviour // TypeDefIndex: 14
{
    // Methods
    public void StartNewGame() { }
}
"""

class NoCoinUnlockTests(unittest.TestCase):
    def setUp(self):
        self.records = find_records(MOCK_METADATA)

    def test_nested_game_types_do_not_shadow_main_game_class(self):
        nested = """// Namespace: SYBO.Subway
private sealed class Game.<StartNewGame>d__12 : IEnumerator // TypeDefIndex: 15
{
    // Methods
    public void MoveNext() { }
}
// Namespace: SYBO.Subway
private sealed class Game.<>c__DisplayClass7_0 // TypeDefIndex: 16
{
    // Methods
    public void StartNewGame() { }
}
// Namespace: SYBO.Subway
public class Game.<OtherCoroutine>d__22 // TypeDefIndex: 17
{
}
"""
        records = find_records(MOCK_METADATA + nested)
        game = exact_record(records, 'SYBO.Subway.Game')
        self.assertEqual(game['kind'], 'class')
        self.assertEqual(len([r for r in records if r['name'] == 'SYBO.Subway.Game']), 1)
        self.assertIn('SYBO.Subway.Game.<StartNewGame>d__12',
                      [r['name'] for r in records])
        self.assertIn('SYBO.Subway.Game.<>c__DisplayClass7_0',
                      [r['name'] for r in records])
        self.assertIn('SYBO.Subway.Game.<OtherCoroutine>d__22',
                      [r['name'] for r in records])
        self.assertIn('StartNewGame()', verify_parameter_types(
            records, 'SYBO.Subway.Game$$StartNewGame', (),
            expect_static=False))

    def test_page_modes_do_not_overwrite_each_other(self):
        self.assertEqual(output_page_for(True).name, "nocoin-unlocks.html")
        self.assertEqual(output_page_for(False).name, "nocoin-unlocks-full.html")

    def test_enum_ids_from_metadata(self):
        verify_upgrade_ids(self.records)
        self.assertEqual(enum_ids(self.records, 'Characters.CharacterId'), [0, 1, 2])
        self.assertEqual(enum_ids(self.records, 'Boards.BoardId'), [2, 3])

    def test_verify_exact_signatures(self):
        self.assertIn('SetKeys(int newAmount)',
                      verify_parameter_types(self.records,
                          'Data.Save.InventorySave$$SetKeys', ('int',)))
        self.assertIn('IncreaseAmount(UpgradeType powerup, int quantity)',
                      verify_parameter_types(self.records,
                          'Data.Save.InventorySave$$IncreaseAmount', ('UpgradeType', 'int')))
        self.assertIn('StartNewGame()',
                      verify_parameter_types(self.records,
                          'SYBO.Subway.Game$$StartNewGame', (), expect_static=False))
        with self.assertRaises(RuntimeError):
            verify_parameter_types(self.records,
                'Data.Save.InventorySave$$IncreaseAmount', ('int', 'UpgradeType'))

    def test_collection_unlock_method_declarations(self):
        expected = {
            "Data.Managers.CharacterManager$$IsCharacterOwned":
                ("Characters.CharacterId",),
            "Data.Managers.CharacterManager$$UnlockCharacter":
                ("Characters.CharacterId",),
            "Data.Managers.BoardManager$$IsBoardOwned":
                ("Boards.BoardId",),
            "Data.Managers.BoardManager$$UnlockBoard":
                ("Boards.BoardId",),
        }
        for method, params in expected.items():
            with self.subTest(method=method):
                self.assertTrue(verify_parameter_types(self.records, method, params))

    def test_signed_leb_large_item_amount(self):
        raw = signed_leb(MAX_ITEMS)
        self.assertEqual(Reader(raw).sint(), MAX_ITEMS)
        self.assertEqual(Reader(signed_leb(-1)).sint(), -1)

    def test_append_scratch_local_preserves_original_instructions(self):
        original = bytes.fromhex('00 20 00 1a 0b')
        scratch = []
        def patch(index):
            scratch.append(index)
            return bytes.fromhex('41 01 1a')
        patched = prepend_to_existing_body(original, patch, 2)
        self.assertEqual(scratch, [2])
        self.assertEqual(patched, bytes.fromhex('01 01 7f 41 01 1a 20 00 1a 0b'))

    def test_append_scratch_after_existing_locals(self):
        original = bytes.fromhex('01 02 7f 20 02 1a 0b')
        scratch = []
        patched = prepend_to_existing_body(original, lambda index: (
            scratch.append(index), b'\x01')[1], 2)
        self.assertEqual(scratch, [4])
        self.assertEqual(patched, bytes.fromhex('02 02 7f 01 7f 01 20 02 1a 0b'))

    def test_grants_are_guarded_instead_of_repeated_unconditional_increases(self):
        targets = {'keys_get': 1, 'keys_set': 2, 'amount_get': 3,
                   'amount_add': 4, 'character_owned': 5, 'character_unlock': 6,
                   'board_owned': 7, 'board_unlock': 8}
        code = build_inventory_preamble(targets, 2, [0, 1], [2, 3])
        self.assertIn(b'\x4e', code)  # signed >= 0
        self.assertIn(b'\x48', code)  # signed < max
        self.assertIn(b'\x45', code)  # ownership check == 0
        self.assertEqual(code.count(b'\x04\x40'), 8)  # keys + 3 items + 2 chars + 2 boards
        self.assertIn(b'\x41' + signed_leb(MAX_ITEMS), code)

if __name__ == '__main__':
    unittest.main()
