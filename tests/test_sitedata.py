import os
import unittest

os.environ.setdefault("DLCLIENT_QUIET", "1")

from dlclient import sitedata as SD  # noqa: E402

INDEX = [
    {"id": 1, "labels": ["area"], "cat": "areas", "toc": {"en": "Drow City", "ua": "Місто Дроу", "ru": "Город Дроу"}},
    {"id": 2, "labels": ["ninja-skills"], "cat": "classes",
     "toc": {"en": "ninja skills", "ua": "вміння ніндзя", "ru": "умения ниндзя"}},
    {"id": 3, "labels": ["religion"], "cat": "religion", "toc": {"en": "Taiphoen", "ua": "Тайфоен", "ru": "Тайфоэн"}},
    {"id": 4, "labels": ["race"], "cat": "races", "toc": {"en": "drow", "ua": "дроу", "ru": "дроу"}},
]

BODY_EN = {
    "1": ("* Levels: 3-20\n* Danger: <c c='r'>high</c>\n* How to get there: Midgaard, 3s2w (from the square)\n\n"
          "Quests:\n* Bring the spider &amp; silk to the matron.  Levels: from 3 to 20. Alignment: evil.\n"
          "  How often: 3 times per life, but no more than once a day.\n\n"
          "* Free the slave. Levels: from 10. First complete the quest: the spider.\n"),
    "2": "Level 1: dagger, kick\nLevel 7: hide, sneak\n",
    "3": "* Paths: shadow\n* Patron of: drow, ninja\n* Gifts: shadow\n* Restrictions: evil only\n\nThe dark one.",
    "4": "* Alignment: evil\n* Stats: str +1, dex +5\n* Classes: ninja, thief\n* Resistant: negative\n* Size: medium\n",
}

BODY_UA = {
    "1": ("* Рівні: 3-20\n\nЗавдання:\n* Принеси шовк.  Рівні: з 3 по 20. Натура: зла.\n"
          "  Як часто: 3 рази за життя.\n"),
    "2": "Рівень 1: кинджал\n",
    "3": "* Шляхи: тінь\n* Дари: тінь\n",
    "4": "* Натура: зла\n* Параметри: сила +1\n",
}

WEAPONS = [
    {"nameEn": "black blade", "name": "черный клинок", "level": 11, "align": "E", "wclass": "sword",
     "ave": "15", "hr": "-", "dr": "2", "areaEn": "Moria", "whereEn": "troll", "vnum": 4100, "limit": 1},
    {"nameEn": "holy sword", "level": 9, "align": "G", "wclass": "sword", "vnum": 1},
    {"nameEn": "plain dagger", "level": 5, "align": "-", "wclass": "dagger", "vnum": 2},
    {"nameEn": "too strong", "level": 30, "align": "", "wclass": "sword", "vnum": 3},
]
ARMOR = [{"nameEn": "mail", "level": 8, "align": "", "wearloc": "torso", "hp": 15, "stat_con": 1, "vnum": 5}]


class ParseTest(unittest.TestCase):
    def site(self, lang="en", body=BODY_EN):
        return SD.Site(lang, INDEX, body, WEAPONS, ARMOR)

    def test_quests(self):
        qs = self.site().zone_quests()
        self.assertEqual(len(qs), 2)
        q = qs[0]
        self.assertEqual(q["zone"], "Drow City")
        self.assertEqual(q["text"], "Bring the spider & silk to the matron.")
        self.assertEqual((q["low"], q["high"]), (3, 20))
        self.assertEqual(q["align"], "evil")
        self.assertEqual(q["often"], "3 times per life, but no more than once a day")
        self.assertEqual(q["danger"], "high")
        self.assertEqual(q["route"], "Midgaard, 3s2w")
        self.assertEqual((qs[1]["low"], qs[1]["high"]), (10, 0))
        self.assertEqual(qs[1]["requires"], "the spider")

    def test_quests_ua(self):
        qs = self.site("ua", BODY_UA).zone_quests()
        self.assertEqual(len(qs), 1)
        self.assertEqual((qs[0]["low"], qs[0]["high"], qs[0]["align"]), (3, 20, "зла"))
        self.assertEqual(qs[0]["zone"], "Місто Дроу")

    def test_skills(self):
        self.assertEqual(self.site().class_names(), ["ninja"])
        self.assertEqual(self.site().class_skills("Ninja"), [(1, ["dagger", "kick"]), (7, ["hide", "sneak"])])
        self.assertEqual(self.site("ua", BODY_UA).class_skills("ninja"), [(1, ["кинджал"])])

    def test_religion_and_race(self):
        r = self.site().religions()[0]
        self.assertEqual((r["name"], r["patron"], r["restrict"]), ("Taiphoen", "drow, ninja", "evil only"))
        race = self.site().races()[0]
        self.assertEqual((race["stats"], race["resist"]), ("str +1, dex +5", "negative"))
        self.assertEqual(self.site("ua", BODY_UA).races()[0]["stats"], "сила +1")

    def test_items(self):
        site = self.site()
        names = [site.item_name(it) for it in site.items("weapon", 5, 11, "evil")]
        self.assertEqual(names, ["black blade", "plain dagger"])
        names = [site.item_name(it) for it in site.items("weapon", 5, 11, "good", wclass="sword")]
        self.assertEqual(names, ["holy sword"])
        self.assertEqual(site.slots("weapon"), ["dagger", "sword"])
        self.assertEqual(site.slots("armor"), ["torso"])
        self.assertEqual(SD.stat_text(WEAPONS[0]), "dam +2")
        self.assertEqual(SD.stat_text(ARMOR[0]), "hp +15, con +1")
        self.assertEqual(self.site("ru", BODY_UA).item_name(WEAPONS[0]), "черный клинок")

    def test_align(self):
        self.assertTrue(SD.usable_by("EN", "neutral"))
        self.assertFalse(SD.usable_by("G", "evil"))
        self.assertTrue(SD.usable_by("-", "evil"))
        self.assertTrue(SD.align_ok("evil", "evil"))
        self.assertFalse(SD.align_ok("evil", "good"))
        self.assertFalse(SD.align_ok("зла", "good"))
        self.assertTrue(SD.align_ok("any", "good"))
        self.assertTrue(SD.align_ok("", "good"))


class GuideTest(unittest.TestCase):
    def test_dialog(self):
        import wx
        from dlclient.guide import GuideDialog
        from dlclient.i18n import Tr
        app = wx.App.Get() or wx.App()
        frame = wx.Frame(None)
        saved = []
        site = SD.Site("en", INDEX, BODY_EN, WEAPONS, ARMOR)
        dlg = GuideDialog(frame, Tr("en"), site, {"level": 11, "class": "ninja", "align": "evil"}, saved.append)
        quests, items, skills, gods, races = dlg.pages
        self.assertEqual(len(quests.rows), 2)
        self.assertIn("Drow City: Bring the spider", quests.rows[0][0])
        self.assertIn("Midgaard, 3s2w", quests.rows[0][1])
        self.assertEqual([r[0].split(",")[0] for r in items.rows], ["black blade"])
        self.assertIn("Limited item", items.rows[0][1])
        self.assertEqual(skills.rows[0][0], "Level 1, reached: dagger, kick")
        self.assertEqual(gods.rows[0][0], "Taiphoen")
        self.assertIn("The dark one.", gods.rows[0][1])
        dlg.set_context({"level": 2, "class": "ninja", "align": "good"})
        self.assertEqual(saved[-1], {"level": 2, "class": "ninja", "align": "good"})
        self.assertEqual(quests.rows, [])
        self.assertEqual(skills.list.GetSelection(), 1)
        quests.search.SetValue("slave")
        quests.fits.SetValue(False)
        quests.refill()
        self.assertEqual(len(quests.rows), 1)
        quests.list.SetSelection(0)
        quests.go_selected()
        self.assertEqual(dlg.choice[:2], ["Drow City", "Drow City"])
        self.assertEqual(dlg.level.number(), 2)
        dlg.level.ChangeValue("abc")
        self.assertEqual(dlg.level.number(), 1)
        dlg.Destroy()
        frame.Destroy()
        del app


if __name__ == "__main__":
    unittest.main()
