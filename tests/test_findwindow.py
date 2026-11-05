import os
import unittest

os.environ.setdefault("DLCLIENT_QUIET", "1")

import wx  # noqa: E402

from dlclient import findviews as FV  # noqa: E402
from dlclient import sitedata as SD  # noqa: E402
from dlclient.findwindow import Action, Filter, FindWindow, Row, View  # noqa: E402
from dlclient.i18n import Tr  # noqa: E402
from tests.test_sitedata import ARMOR, BODY_EN, INDEX, WEAPONS  # noqa: E402

AREAS = [
    {"name": "Midennir", "en": "Midennir", "ru": "Миденнир", "min": 5, "max": 15, "levels": True,
     "route": "14s", "steps": 14, "note": "", "danger": "hard"},
    {"name": "UnderDark", "en": "UnderDark", "ru": "Подземье", "min": 13, "max": 50, "levels": True,
     "route": "ns6e10nd", "steps": 19, "note": "or s4sdwdn7d", "danger": "hard"},
    {"name": "Limbo", "en": "Limbo", "ru": "Лимб", "min": 0, "max": 0, "levels": False,
     "route": "", "steps": None, "note": "Pray to reach it.", "danger": ""},
]


class FindWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)
        cls.frame = wx.Frame(None)
        cls.tr = Tr("en")

    @classmethod
    def tearDownClass(cls):
        cls.frame.Destroy()

    def test_typeahead_and_actions(self):
        said = []
        state = {"big": False}
        rows = [Row("apple pie", 1), Row("Яблуко, ukrainian", 2), Row("big stone", 3)]
        view = View("t", "Things", lambda: [r for r in rows if not state["big"] or "big" in r.label],
                    lambda p: "detail %s" % p,
                    actions=[Action("use", "&Use", can=lambda p: p != 2)],
                    filters=[Filter("big", "Only big", "check", lambda: state["big"], lambda v: state.update(big=v))])
        w = FindWindow(self.frame, self.tr, "Find", [view], say=said.append)
        p = w.panel()
        self.assertEqual(len(p.shown), 3)
        p.search.SetValue("ябл")
        self.assertEqual([r.payload for r in p.shown], [2])
        p.search.SetValue("")
        p.list.SetSelection(1)
        p.run(view.actions[0])
        self.assertIsNone(w.result)
        self.assertIn("Not available", said[-1])
        p.list.SetSelection(2)
        p.run(view.actions[0])
        self.assertEqual(w.result, ("t", "use", 3))
        view.filters[0].set(True)
        w.refill_all()
        self.assertEqual([r.payload for r in p.shown], [3])
        self.assertIn("Only big: yes", p.filters_line.GetLabel())
        w.Destroy()

    def test_keys(self):
        rows = [Row("Яблуко", 1), Row("apple", 2)]
        w = FindWindow(self.frame, self.tr, "Find", [View("t", "Things", lambda: rows, str)])
        p = w.panel()
        ev = wx.KeyEvent(wx.wxEVT_CHAR)
        ev.SetUnicodeKey(ord("я"))
        p.on_list_char(ev)
        self.assertEqual(p.search.GetValue(), "я")
        self.assertEqual([r.payload for r in p.shown], [1])
        back = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
        back.SetKeyCode(wx.WXK_BACK)
        p.on_list_key(back)
        self.assertEqual(p.search.GetValue(), "")
        self.assertEqual(len(p.shown), 2)
        w.Destroy()

    def test_rooms(self):
        rooms = [{"vnum": 1, "name": "Market Square", "steps": 0, "desc": "The centre.", "exits": ["north"]},
                 {"vnum": 2, "name": "Temple Square", "steps": 1, "desc": "", "exits": []}]
        v = FV.rooms_view(self.tr, rooms)
        labels = [r.label for r in v.rows()]
        self.assertEqual(labels, ["Market Square, you are here", "Temple Square, 1 step"])
        self.assertIn("The centre.", v.detail(rooms[0]))
        self.assertIn("Exits: north.", v.detail(rooms[0]))

    def test_areas(self):
        saved = []
        v = FV.areas_view(self.tr, AREAS, {"sort": "level"}, saved.append)
        self.assertEqual([r.payload["name"] for r in v.rows()], ["Midennir", "UnderDark", "Limbo"])
        v.filters[0].set((10, 60))
        self.assertEqual([r.payload["name"] for r in v.rows()], ["UnderDark"])
        self.assertEqual(saved[-1]["levels"], (10, 60))
        limbo = AREAS[2]
        self.assertFalse(v.actions[0].can(limbo))
        self.assertIn("Pray to reach it.", v.detail(limbo))

    def test_guide(self):
        site = SD.Site("en", INDEX, BODY_EN, WEAPONS, ARMOR)
        ctxs, optss = [], []
        views, update = FV.guide_views(self.tr, site, {"level": 11, "class": "ninja", "align": "evil"}, {},
                                       ctxs.append, optss.append)
        quests, items, skills, gods, races = views
        self.assertEqual([f.key for f in quests.filters[:3]], ["level", "class", "align"])
        self.assertEqual(len(quests.rows()), 2)
        self.assertEqual([r.payload["nameEn"] for r in items.rows()], ["black blade", "plain dagger"])
        kind = next(f for f in items.filters if f.key == "kind")
        kind.set("armor")
        self.assertEqual(optss[-1]["kind"], "armor")
        self.assertEqual([r.payload["nameEn"] for r in items.rows()], ["mail"])
        stat = next(f for f in items.filters if f.key == "stat")
        stat.set("overall")
        self.assertEqual([r.payload["nameEn"] for r in items.rows()], ["mail"])
        go = items.actions[0]
        self.assertEqual(go.value(ARMOR[0]), [])
        self.assertFalse(go.can(ARMOR[0]))
        quests.filters[0].set(2)
        self.assertEqual(ctxs[-1]["level"], 2)
        self.assertEqual(quests.rows(), [])  # nothing fits level 2 and evil
        update({"level": 11, "class": "Ninja"})
        self.assertEqual(len(quests.rows()), 2)
        self.assertEqual([r.label for r in skills.rows()][:1], ["Level 1, reached: dagger"])
        self.assertEqual(gods.rows()[0].label, "Taiphoen")
        self.assertIn("The dark one.", gods.detail(gods.rows()[0].payload))
        w = FindWindow(self.frame, self.tr, "Guide", views, tab_keys={"Q": "quests", "R": "races"})
        self.assertTrue(w.select_view("races"))
        self.assertEqual(w.panel().view.key, "races")
        w.Destroy()

    def test_item_search(self):
        site = SD.Site("en", INDEX, BODY_EN, WEAPONS, ARMOR)
        v = FV.item_search_view(self.tr, site)
        w = FindWindow(self.frame, self.tr, "Find an item", [v])
        p = w.panel()
        self.assertEqual(len(p.shown), len(WEAPONS) + len(ARMOR))
        p.search.SetValue("ЧЕРНЫЙ")
        self.assertEqual([r.payload["vnum"] for r in p.shown], [4100])
        p.search.SetValue("nothing like it")
        self.assertEqual(p.shown, [])
        self.assertIn("Random items", p.list.GetString(0))
        w.Destroy()


if __name__ == "__main__":
    unittest.main()
