import unittest

from dlclient.areamap import fix_routes, route_breaks

# Temple Square 3005 north of the Market Square 3014; south of the square is a
# road with a dead-end shop to its east, and from the temple square the same
# route reaches another way out of town (9999, not on the map).
ROOMS = {
    3014: {"north": 3005, "south": 3065},
    3005: {"south": 3014},
    3065: {"east": 3066, "north": 3014},
    3066: {"west": 3065},
}


class RouteFixTest(unittest.TestCase):
    def test_breaks(self):
        self.assertTrue(route_breaks("s2e", ROOMS))
        self.assertFalse(route_breaks("se", ROOMS))
        self.assertFalse(route_breaks("2s", {3014: {"south": 1}}))

    def test_fix(self):
        rooms = dict(ROOMS)
        rooms[3005] = {"south": 3014, "east": 9999}
        areas = [{"route": "es", "steps": 2}, {"route": "se", "steps": 2}, {"route": "ww", "steps": 2}, {"route": None}]
        fix_routes(areas, rooms)
        self.assertEqual(areas[0], {"route": "nes", "steps": 3})
        self.assertEqual(areas[1]["route"], "se")
        self.assertEqual(areas[2]["route"], "ww")


if __name__ == "__main__":
    unittest.main()
