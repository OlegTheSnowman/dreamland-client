import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dlclient.markup import OutputParser
from dlclient.presence import classify

ROOM = (
    "<m i=\"Samuro\" c=\"look $,follow $,whois $\">Samuro</m> is standing here.\n"
    "<m i=\"123456\" c=\"look $,consider $,smell $,follow $\">A guard</m> keeps order here.\n"
    "<m i=\"98765\" c=\"get $,look $\">A sword</m> lies here.\n"
)


class PresenceTest(unittest.TestCase):
    def kinds(self, text):
        return classify(OutputParser().parse(text)[0])

    def test_room(self):
        self.assertEqual(self.kinds(ROOM), {"player", "mob", "item"})

    def test_target_in_other_languages(self):
        self.assertEqual(self.kinds("[ЦІЛЬ] <m i=\"5\" c=\"look $,шанси $\">Пес</m> тут.\n"), {"target", "mob"})

    def test_plain_text(self):
        self.assertEqual(self.kinds("A quiet street.\n"), set())


if __name__ == "__main__":
    unittest.main()
