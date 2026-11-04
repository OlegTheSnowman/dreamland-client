import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dlclient.areamap import route_steps, split_route
from dlclient.mapview import AreaMap

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

    def test_names_and_moves(self):
        self.assertEqual(self.m.name, "Test")
        self.assertEqual(self.m.step(1, "north"), 2)
        self.assertEqual(self.m.step(1, "east"), 3)
        self.assertIsNone(self.m.step(1, "south"))
        self.assertEqual(self.m.step(2, "up"), 4)
        self.assertEqual(self.m.step(3, "north"), 2)

    def test_steps(self):
        self.assertEqual(self.m.steps_from(1), {1: 0, 2: 1, 3: 1, 4: 2})


class RouteTest(unittest.TestCase):
    def test_split(self):
        self.assertEqual(split_route("3nu"), ("3nu", ""))
        self.assertEqual(split_route("s6sese or by metro"), ("s6sese", "or by metro"))
        self.assertEqual(split_route("s13w, enter tree"), ("s13w", "enter tree"))
        self.assertEqual(split_route("use the portal"), (None, "use the portal"))
        self.assertEqual(route_steps("s6sese"), 10)


if __name__ == "__main__":
    unittest.main()
