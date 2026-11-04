import unittest

from dlclient import framelists
from dlclient.i18n import Tr


def frame(kind, rows):
    return {"kind": kind, "title": "", "rows": rows}


class FrameListsTest(unittest.TestCase):
    def setUp(self):
        self.tr = Tr("en")

    def test_skill_row(self):
        rows = framelists.rows_from_frame(frame("skills", [{
            "label": "bash, 75% (80%)", "id": "bash", "section": "6",
            "data": {"level": 6, "available": True, "learned": 75, "real": 80, "moves": 13},
            "actions": [{"verb": "practice", "cmd": "practice bash"}, {"verb": "help", "cmd": "help 42"}]}]),
            self.tr, "skills")
        row = rows[0]
        self.assertTrue(row["label"].startswith("bash, 75% (80%), "))
        self.assertIn("13", row["label"])
        self.assertEqual(row["keys"][(ord("P"), True)], ["practice bash"])
        self.assertEqual(row["keys"][(ord("H"), True)], ["help 42"])
        self.assertEqual(row["refresh"], {"practice bash"})
        self.assertEqual([cmd for _, cmd in row["menu"]], ["practice bash", "help 42"])

    def test_cyrillic_label_and_section(self):
        rows = framelists.rows_from_frame(frame("commands", [{
            "label": "вдягнути", "section": "Речі", "actions": [{"verb": "help", "cmd": "help wear"}]}]),
            Tr("ua"), "commands")
        self.assertEqual(rows[0]["label"], "вдягнути, Речі")

    def test_unknown_verb_shows_command(self):
        rows = framelists.rows_from_frame(frame("x", [{"label": "a", "actions": [{"verb": "dance", "cmd": "dance a"}]}]),
                                          self.tr, "x")
        self.assertEqual(rows[0]["menu"], [("dance a", "dance a")])
        self.assertEqual(rows[0]["keys"], {})

    def test_open_close_and_input(self):
        rows = framelists.rows_from_frame(frame("glist", [
            {"label": "combat", "actions": [{"verb": "open", "cmd": "glist combat"}]},
            {"label": "offer", "actions": [{"verb": "request", "cmd": "quest request 1"}]},
            {"label": "Oris", "actions": [{"verb": "tell", "cmd": "tell Oris"},
                                          {"verb": "social_at", "cmd": "smile"}]}]), self.tr, "glist")
        self.assertEqual(rows[0]["open"], ("glist", "glist combat"))
        self.assertTrue(rows[1]["close"])
        self.assertEqual([cmd for _, cmd in rows[2]["menu"]], ["__input__ tell Oris", "__target__ smile"])

    def test_empty_and_bad_rows(self):
        self.assertEqual(framelists.rows_from_frame({"rows": None}, self.tr, "x"), [])
        rows = framelists.rows_from_frame(frame("x", ["junk", {"label": "a", "actions": [{"verb": "help"}]}]),
                                          self.tr, "x")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["menu"], [])


if __name__ == "__main__":
    unittest.main()
