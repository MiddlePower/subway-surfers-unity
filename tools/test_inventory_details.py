#!/usr/bin/env python3
"""Synthetic unit tests for the read-only inventory signature reporter."""
import tempfile
import unittest
from pathlib import Path

from inspect_inventory_details import parse_dump, is_relevant, priority


MOCK_DUMP = """// Namespace: Data.Save
public class InventorySave // TypeDefIndex: 42
{
    // Fields
    public static int keys { get; set; }
    // Methods
    public static void SetKeys(int value) { }
    public static int GetAmount(UpgradeType type) { }
}
// Namespace:
public enum UpgradeType // TypeDefIndex: 43
{
    // Fields
    public const UpgradeType Hoverboard = 1; // 0x0
    public const UpgradeType ScoreBooster = 2; // 0x0
}
// Namespace: UI.Popups
public class ShopPopup // TypeDefIndex: 44
{
    // Methods
    public void Open() { }
}
"""


class InventoryReportTests(unittest.TestCase):
    def test_metadata_parser(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "dump.cs"
            path.write_text(MOCK_DUMP, encoding="utf-8")
            records = parse_dump(path)
        names = [record["name"] for record in records]
        self.assertEqual(names, ["Data.Save.InventorySave", "UpgradeType", "UI.Popups.ShopPopup"])
        self.assertTrue(is_relevant(records[0]))
        self.assertTrue(is_relevant(records[1]))
        self.assertFalse(is_relevant(records[2]))
        self.assertTrue(any("SetKeys(int value)" in line for line in records[0]["lines"]))
        self.assertTrue(any("Hoverboard = 1" in line for line in records[1]["lines"]))
        self.assertLessEqual(priority(records[0]), -90)


if __name__ == "__main__":
    unittest.main()
