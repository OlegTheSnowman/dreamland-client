import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dlclient.i18n import Tr
from dlclient.mapview import AreaMap, describe

GRAPH = {
    "meta": {"name": "Тест", "i18n": {"en": {"name": "Test"}}},
    "rooms": {
        "1": {"vnum": 1, "name": "Площадь", "sector": "city", "i18n": {"en": {"name": "Square"}},
              "exits": [{"dir": "north", "target": 2}, {"dir": "east", "target": 3}, {"dir": "west", "target": 900}]},
        "2": {"vnum": 2, "name": "Храм", "sector": "inside", "i18n": {"en": {"name": "Temple"}},
              "exits": [{"dir": "south", "target": 1}, {"dir": "up", "target": 4}]},
        "3": {"vnum": 3, "name": "Склад", "sector": "city", "i18n": {"en": {"name": "Store"}},
              "exits": [{"dir": "west", "target": 1}]},
        "4": {"vnum": 4, "name": "Крыша", "sector": "air", "i18n": {"en": {"name": "Roof"}},
              "exits": [{"dir": "down", "target": 2}]},
    },
    "placed": {"1": {"x": 0, "y": 0, "z": 0}, "2": {"x": 0, "y": 2, "z": 0},
               "3": {"x": 2, "y": 0, "z": 0}, "4": {"x": 0, "y": 2, "z": 1}},
    "exits": [
        {"from": 1, "to": 2, "dir": "north", "style": "open", "bidirectional": True},
        {"from": 1, "to": 3, "dir": "east", "style": "door_locked", "bidirectional": True},
        {"from": 1, "to": 900, "dir": "west", "style": "cross_area", "targetArea": "haon"},
        {"from": 2, "to": 4, "dir": "up", "style": "open", "bidirectional": True},
    ],
}


class MapTest(unittest.TestCase):
    def setUp(self):
        self.m = AreaMap(GRAPH, "en", {"haon": "Haon Dor"})
        self.tr = Tr("en")

    def test_names_and_moves(self):
        self.assertEqual(self.m.name, "Test")
        self.assertEqual(self.m.step(1, "north"), 2)
        self.assertEqual(self.m.step(1, "east"), 3)
        self.assertIsNone(self.m.step(1, "south"))
        self.assertEqual(self.m.step(2, "up"), 4)
        self.assertEqual(self.m.step(3, "north"), 2)

    def test_spoken(self):
        here = describe(self.m, 1, 1, self.tr)
        self.assertEqual(here, "Square. city. you are here. Exits: north, east locked door, west leads to Haon Dor.")
        self.assertIn("north of you, 1 step", describe(self.m, 2, 1, self.tr))
        self.assertIn("north of you, 1 level up, 2 steps", describe(self.m, 4, 1, self.tr))
        self.assertIn("Exits: west locked door.", describe(self.m, 3, 1, self.tr))


if __name__ == "__main__":
    unittest.main()
