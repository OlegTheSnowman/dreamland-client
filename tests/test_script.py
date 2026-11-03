import base64
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dlclient.script import ScriptHost


class ScriptTest(unittest.TestCase):
    def host(self):
        self.out = []
        add = lambda kind: (lambda *a: self.out.append((kind,) + a))
        return ScriptHost(add("send"), add("echo"), add("notify"), add("autobuff"), lambda: "typed",
                          add("set"), add("error"), os.path.join(ROOT, "no-cache"),
                          os.path.join(ROOT, "dlclient", "defaults.js"))

    def test_stock_keypad_and_commands(self):
        h = self.host()
        self.assertTrue(h.load(h.stock_text(), "stock"))
        self.assertTrue(h.on_key(98, "Numpad2", False, False, False))
        self.assertTrue(h.on_key(104, "Numpad8", False, True, False))
        self.assertFalse(h.on_key(112, "", False, False, False))
        self.assertTrue(h.on_input("/victim orc"))
        self.assertFalse(h.on_input("look"))
        sends = [x[1] for x in self.out if x[0] == "send"]
        self.assertEqual(sends, ["south", "scan north"])

    def test_account_copy_replaces_stock(self):
        h = self.host()
        h.load(h.stock_text(), "stock")
        own = "keydown = function (e) { if (e.which == 112) { send('mine'); e.preventDefault(); } };"
        h.on_script_data({"account": 1, "b64": base64.b64encode(own.encode()).decode()})
        self.assertEqual(h.source, "account")
        self.assertTrue(h.on_key(112, "", False, False, False))
        self.assertFalse(h.on_key(98, "Numpad2", False, False, False))

    def test_runaway_and_broken_scripts(self):
        h = self.host()
        self.assertFalse(h.load("while (true) {}", "account"))
        self.assertFalse(h.load("this is not javascript", "account"))
        self.assertTrue(h.load("keydown = function () { while (true) {} };", "account"))
        self.assertFalse(h.on_key(1, "", False, False, False))


if __name__ == "__main__":
    unittest.main()
