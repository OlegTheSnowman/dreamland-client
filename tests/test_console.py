import os
import sys
import unittest

os.environ["DLCLIENT_QUIET"] = "1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import wx

from dlclient import ui


class ConsoleSmokeTest(unittest.TestCase):
    """Game text must reach the output; a missing helper in the console path
    once swallowed every line."""

    @classmethod
    def setUpClass(cls):
        cls.app = wx.App(False)
        ui.MainFrame.connect = lambda self: None
        cls.frame = ui.MainFrame(ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.frame.Destroy()

    def test_text_reaches_output(self):
        f = self.frame
        f.on_frame("console_out", ["Dark Temple\nThis is a great, cold Temple.\n<53hp> "])
        texts = [t for t, _ in f.lines]
        self.assertIn("Dark Temple", texts)

    def test_server_lists_off_by_default(self):
        f = self.frame
        f.prefs.pop("server_lists", None)
        self.assertFalse(f.server_lists())
        f.capture = {"kind": "skills", "lines": []}
        f.on_frame("list", [{"kind": "skills", "rows": []}])
        self.assertNotIn("frame", f.capture)
        f.prefs["server_lists"] = True
        f.on_frame("list", [{"kind": "skills", "rows": []}])
        self.assertIn("frame", f.capture)
        f.capture = None
        f.prefs.pop("server_lists", None)

    def test_stopped_run_is_remembered(self):
        f = self.frame
        f.conn.send_line = lambda t: True
        f.on_frame("console_out", ["You still have left to run: <hs>4es</hs>\n"])
        self.assertEqual(f.run_left, "run 4es")


if __name__ == "__main__":
    unittest.main()
