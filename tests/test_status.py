import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dlclient import status
from dlclient.i18n import Tr

PROMPT = {
    "pro": [{"n": "armor", "d": 5}, {"n": "sanct", "f": "sanctuary", "d": 1}],
    "mal": [{"n": "poison", "d": 2}],
    "det": [{"n": "infra", "d": -1}],
    "q": {"t": 12, "i": "Find the sceptre"},
    "room": "{WMarket Square{x", "zone": "Midgaard", "exits": {"e": "nesw", "h": "u"},
    "group": "none",
}


class StatusTest(unittest.TestCase):
    def test_affects_order(self):
        text = status.affects(PROMPT, Tr("en"))
        self.assertEqual(text, "Effects: poison, harmful, 2 hours; sanctuary, 1 hour; armor, 5 hours; infra, permanent.")

    def test_other_panels(self):
        tr = Tr("en")
        self.assertEqual(status.quests(PROMPT, tr), "Questor task: Find the sceptre. 12 minutes left.")
        self.assertEqual(status.location(PROMPT, tr), "Market Square. Midgaard. Exits: north, east, south, west. Hidden exits: up.")
        self.assertEqual(status.group(PROMPT, tr), "You are not in a group.")

    def test_russian_hours(self):
        tr = Tr("ru")
        self.assertEqual(status.hours(tr, 1), "1 час")
        self.assertEqual(status.hours(tr, 3), "3 часа")
        self.assertEqual(status.hours(tr, 11), "11 часов")


if __name__ == "__main__":
    unittest.main()
