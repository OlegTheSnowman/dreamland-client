"""The main window's rooms, areas, guide and item search flows, with the modal
find window answered by the test instead of the player."""
import os
import sys
import unittest

os.environ["DLCLIENT_QUIET"] = "1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import wx  # noqa: E402

from dlclient import findwindow, sitedata as SD, ui  # noqa: E402
from tests.test_findwindow import AREAS  # noqa: E402
from tests.test_sitedata import ARMOR, BODY_EN, INDEX, WEAPONS  # noqa: E402


class FindFlowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)
        ui.MainFrame.connect = lambda self: None
        cls.frame = ui.MainFrame(ROOT)
        cls.answer = None
        cls.shown = []

        def show(win, view_key=None):
            cls.shown.append(win)
            if view_key:
                win.select_view(view_key)
            win.result = cls.answer(win) if cls.answer else None
            return wx.ID_OK
        cls.orig = (findwindow.FindWindow.ShowModal, findwindow.FindWindow.show_again)
        findwindow.FindWindow.ShowModal = lambda win: show(win)
        findwindow.FindWindow.show_again = show

    @classmethod
    def tearDownClass(cls):
        findwindow.FindWindow.ShowModal, findwindow.FindWindow.show_again = cls.orig
        cls.frame.Destroy()

    def setUp(self):
        f = self.frame
        self.sent, self.walked, self.zones = [], [], []
        f.send_command = self.sent.append
        f.walk_area = lambda area, how: self.walked.append((area["name"], how))
        f.walk_to_zone = self.zones.append
        f.say = lambda *a: None

    def test_rooms(self):
        rooms = [{"vnum": 3001, "name": "Temple", "steps": 2, "desc": "", "exits": []}]
        type(self).answer = staticmethod(lambda w: ("rooms", "walk", w.panel().shown[0].payload))
        self.frame._rooms_loaded(rooms)
        self.assertEqual(self.sent, ["path 3001"])
        self.assertEqual(self.frame.walk_name, "Temple")

    def test_areas(self):
        for how, want in (("walk", ui.AREA_WALK), ("route", ui.AREA_ROUTE)):
            type(self).answer = staticmethod(lambda w, how=how: ("areas", how, w.panel().shown[0].payload))
            self.frame._areas_loaded(AREAS)
            self.assertEqual(self.walked[-1][1], want)
        def sort_then_help(w):
            sort = next(f for f in w.panel().view.filters if f.key == "sort")
            sort.set("level")
            return ("areas", "help", AREAS[0])
        type(self).answer = staticmethod(sort_then_help)
        self.frame._areas_loaded(AREAS)
        self.assertEqual(self.sent, ["help Midennir"])
        self.assertEqual(self.frame.prefs["areas_find"]["sort"], "level")

    def test_guide_and_lookup(self):
        f = self.frame
        site = SD.Site("en", INDEX, BODY_EN, WEAPONS, ARMOR)
        f.guide_keep = f.lookup_keep = None
        f.prefs["guide_opts"] = {}
        go = staticmethod(lambda w: ("items", "go", ["Zone A"]))
        type(self).answer = go
        f._guide_loaded(site, "items")
        self.assertEqual(self.zones, [["Zone A"]])
        self.assertEqual(f.guide_keep.panel().view.key, "items")
        f.guide_name = "edwin"
        f.guide_char({"current": "Edwin", "chars": [{"name": "Edwin", "level": "12", "class": "ninja"}]})
        self.assertEqual(f.guide_context()["level"], 12)
        f._guide_show(f.guide_keep, tab="quests")
        self.assertEqual(len(self.zones), 2)
        f._lookup_loaded(site)
        self.assertIsNotNone(f.lookup_keep)
        self.assertEqual(len(self.zones), 3)
        type(self).answer = None
        f._guide_show(f.lookup_keep)
        self.assertEqual(len(self.zones), 3)


if __name__ == "__main__":
    unittest.main()
