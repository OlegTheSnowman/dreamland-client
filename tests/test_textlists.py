import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dlclient import textlists as T
from dlclient.i18n import Tr
from dlclient.markup import OutputParser

SHOP = """Armourer offers:
1. pair of white goat-wool gloves. Level 85. 23 gold and 10 silver. 1 left. (worn on the hands, yours at level 82)
5. small wooden shield. Level 3. 43 silver. (used as a shield)
19. lamellar breastplate. Level 5. 1 gold and 11 silver. (worn on the body, worse than worn)
Tell a vendor the name of an item, and they'll tell you everything about it for 1% of its price.
"""
SERVICE = """You turn to healer for services.
Healer says 'I offer the following services:'
   service refresh         5 gold
   service heal            10 gold
   service repair          price by arrangement
"""
TRAIN = """Guildmaster says 'You have 0 training sessions, 9 practice sessions and 152 quest points.'
train con             : 25/27  raise per training session
wis                    : 24/24  (at maximum)
train str             : 21/25  raise per training session
"""
SKILLS = """===============================================================================
  Level| Skill             | Learned |Cost| Skill             | Learned |Cost
-------+--------------------+---------+----+--------------------+---------+----
    1  | infravision       | 100(100)| 20 | recall            |  75( 75)|  4m
       | dagger            |  75( 75)|    | enchant weapon    | 100(100)| 100
    6  | mace              |   1(  1)|    | bash              |   1(  1)| 13m
       | bash door         |  75( 75)| 20 |                   |         |
"""
QS = """You ask mermaid to show the list of items.
List of quest items available for purchase:
Hero gear
1. Hero's Girth, word girth: 500 qp.
9. 10 practices, word practice: 100 qp.
Services
5. Personal vault, word vault: 1000 qp.
You have 152 quest points.
To buy something, use quest buy word or a number.
"""
QR = """Mermaid tells you 'Here's what tasks I can give you today:'
      1. Assassination             (moderate) 
      5. Royal Treasures           (easy) 
"""
ZQ = """Zone Quests
[ 1500] Prisoner of the Hobgoblins, zone Gnome Village, levels 1-15
The Elder reckons you can slip past the jailer by dressing the gnome
as a hobgoblin soldier.
Commands: quest 1500, quest cancel 1500
"""
AR = """All Dreamland zones:
Name                    Difficulty       Name                    Difficulty
Machine Dreams             1-10   safe   Zoology Museum             1-10   easy
Ruins of the Arcane Tow  95-100 deadly   Wyvern Tower               5-30   hard
Quifael Area                      safe   Redferne Residence        1-100   safe
"""


def rows(fn, text):
    return [(r["label"], r["menu"][0][1] if r["menu"] else None) for r in fn(OutputParser().parse(text)[0], Tr("en"))]


class TextListTest(unittest.TestCase):
    def test_shop(self):
        got = rows(T.shop, SHOP)
        self.assertEqual(len(got), 3)
        self.assertEqual(got[1][1], "buy 5")

    def test_services(self):
        self.assertEqual(rows(T.services, SERVICE)[0], ("refresh, 5 gold", "service refresh"))

    def test_training(self):
        self.assertEqual(rows(T.training, TRAIN), [("con 25/27 raise per training session", "train con"),
                                                   ("wis 24/24 (at maximum)", None),
                                                   ("str 21/25 raise per training session", "train str")])

    def test_skills(self):
        got = dict((label.split(",")[0], cmd) for label, cmd in rows(T.skills, SKILLS))
        self.assertEqual(got["bash door"], "practice 'bash door'")
        self.assertEqual(got["bash"], "practice bash")

    def test_quest_lists(self):
        self.assertEqual(rows(T.quest_shop, QS)[1][1], "quest buy 9")
        self.assertTrue(rows(T.zone_quests, ZQ)[0][0].startswith("Prisoner of the Hobgoblins"))



if __name__ == "__main__":
    unittest.main()
