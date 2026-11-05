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

    def test_teachers(self):
        index = INDEX + [{"id": 9, "labels": ["skillgroup"], "cat": "classes", "toc": {"en": "Adventure"}}]
        body = dict(BODY_EN)
        body["2"] = ("Level </c><c c='fgbc'>7</c><c c='fgdx'>: </c><hh id='703'><c c='fgdx'>sneak</c></hh>"
                     "<c c='fgdx'>, </c><hh id='798'><c c='fgdx'>hide</c></hh>\n")
        body["9"] = ("Group <c c='fgby'>adventure</c>\n\nTeacher - </c><c c='fgdg'>Hassan</c><c c='fgdx'> (</c>"
                     "<hh id='1'><c c='fgby'>Drow City</c></hh><c c='fgdx'>).\n\nSkills:\n<hh id='703'>sneak</hh>\n")
        site = SD.Site("en", index, body, [], [])
        self.assertEqual(site.class_skill_list("ninja"),
                         [{"level": 7, "name": "sneak", "id": 703}, {"level": 7, "name": "hide", "id": 798}])
        t = site.skill_teachers()[703]
        self.assertEqual((t["teacher"], t["zone_id"], t["group"]), ("Teacher - Hassan (Drow City).", 1, "Adventure"))
        self.assertNotIn(798, site.skill_teachers())
        self.assertEqual(site.zone_names(1)[:2], ["Drow City", "Drow City"])

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
    """The guide's views (findviews.guide_views) on the fixture data."""

    def test_views(self):
        from dlclient import findviews as FV
        from dlclient.guide import item_detail
        from dlclient.i18n import Tr
        tr = Tr("en")
        site = SD.Site("en", INDEX, BODY_EN, WEAPONS, ARMOR)
        ctxs, optss = [], []
        views, update = FV.guide_views(tr, site, {"level": 11, "class": "ninja", "align": "evil"}, {},
                                       ctxs.append, optss.append)
        quests, items, skills, gods, races = views
        rows = quests.rows()
        self.assertEqual(len(rows), 2)
        self.assertIn("Drow City: Bring the spider", rows[0].label)
        self.assertIn("Midgaard, 3s2w", quests.detail(rows[0].payload))
        # From level 1 by default: the level 5 dagger is listed too.
        self.assertEqual([r.label.split(",")[0] for r in items.rows()], ["black blade", "plain dagger"])
        self.assertIn("Limited item", items.detail(items.rows()[0].payload))
        self.assertEqual([r.label for r in skills.rows()[:3]],
                         ["Level 1, reached: dagger", "Level 1, reached: kick", "Level 7, reached: hide"])
        self.assertEqual(gods.rows()[0].label, "Taiphoen")
        self.assertIn("The dark one.", gods.detail(gods.rows()[0].payload))
        stat = next(f for f in items.filters if f.key == "stat")
        stat.set("dr")
        self.assertEqual([r.label.split(",")[0] for r in items.rows()], ["black blade"])
        stat.set("hr")  # neither weapon has any hitroll
        self.assertEqual(items.rows(), [])
        stat.set("overall")  # the blade (dam +2) ranks, the bare dagger does not
        self.assertEqual([r.label.split(",")[0] for r in items.rows()], ["black blade"])
        stat.set("")
        self.assertEqual(site.class_weapons("ninja"), [])  # the fixture's skills are not weapons
        self.assertEqual(site.zone_info("Drow City"), ("3-20", "high"))
        self.assertIn("Zone: 3-20, high.", item_detail(tr, site, {"nameEn": "x", "level": 5, "areaEn": "Drow City",
                                                                   "vnum": 1}, "armor"))
        self.assertTrue(SD.has_minus({"hr": -1}))
        self.assertEqual(SD.stat_gain({"saves": -2}, "saves"), 2)
        quests.filters[0].set(2)
        quests.filters[2].set("good")
        self.assertEqual(ctxs[-1], {"level": 2, "class": "ninja", "align": "good"})
        self.assertEqual(quests.rows(), [])
        fits = next(f for f in quests.filters if f.key == "fits")
        fits.set(False)
        slave = [r for r in quests.rows() if "slave" in r.search]
        self.assertEqual(len(slave), 1)
        self.assertEqual(quests.actions[0].value(slave[0].payload)[:2], ["Drow City", "Drow City"])
        update({"level": 11})
        self.assertEqual(quests.filters[0].get(), 11)

    def test_saved_options(self):
        from dlclient import findviews as FV
        from dlclient.i18n import Tr
        site = SD.Site("en", INDEX, BODY_EN, WEAPONS, ARMOR)
        optss = []
        views, _update = FV.guide_views(Tr("en"), site, {"level": 11}, {"kind": "armor", "nominus": True,
                                                                         "fits": False, "stat": "hp"},
                                        lambda c: None, optss.append)
        quests, items = views[:2]
        get = lambda v, k: next(f for f in v.filters if f.key == k).get()
        self.assertEqual((get(items, "kind"), get(items, "nominus"), get(quests, "fits"), get(items, "stat")),
                         ("armor", True, False, "hp"))
        self.assertEqual([r.label.split(",")[0] for r in items.rows()], ["mail"])
        next(f for f in quests.filters if f.key == "fits").set(True)
        self.assertTrue(optss[-1]["fits"] and optss[-1]["kind"] == "armor")


if __name__ == "__main__":
    unittest.main()


class StatsTest(unittest.TestCase):
    def test_parse_stats(self):
        from dlclient.sitedata import parse_stats
        want = {"str": -1, "int": 5, "wis": 1, "dex": 1, "con": -1}
        self.assertEqual(parse_stats("-1 to str, +5 to int, +1 to wis, +1 to dex, -1 to con"), want)
        self.assertEqual(parse_stats("-1 к силе, +5 к интеллекту, "
                                     "+1 к мудрости, +1 к ловкости, "
                                     "-1 к сложению"), want)
        self.assertEqual(parse_stats("+2 до силі, +1 до інтелекту, "
                                     "+1 до спритності, +1 до статурі"),
                         {"str": 2, "int": 1, "dex": 1, "con": 1})
