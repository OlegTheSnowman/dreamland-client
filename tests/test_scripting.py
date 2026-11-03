import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dlclient import scripting as s  # noqa: E402


class Later:
    def __init__(self):
        self.calls = []

    def __call__(self, secs, fn):
        self.calls.append(fn)

    def run(self):
        calls, self.calls = self.calls, []
        for fn in calls:
            fn()


class TriggerTest(unittest.TestCase):
    def store(self, items, scope="char"):
        sent = []
        later = Later()
        t = s.Triggers(lambda *a: sent.append(a) or True, later)
        t.on_data({"account": True, scope: {"b64": s.b64_encode({"v": 1, "list": items})}})
        return t, sent, later

    def test_plain_pattern_placeholders(self):
        t, _, _ = self.store([{"id": "a", "pattern": "%1 tells you '%2'", "cmd": "tell %1 got %2"}])
        fired, _, _ = t.run(["Vasya tells you 'hello there'"])
        self.assertEqual(fired[0][1], "tell Vasya got hello there")

    def test_regex_and_case(self):
        t, _, _ = self.store([{"id": "a", "pattern": r"^You are (\w+)\.$", "regex": True, "cmd": "say %1"},
                              {"id": "b", "pattern": "HUNGRY", "cmd": "eat bread"}])
        fired, _, _ = t.run(["You are hungry."])
        self.assertEqual([f[1] for f in fired], ["say hungry", "eat bread"])

    def test_once_per_block_and_highlight(self):
        t, _, _ = self.store([{"id": "a", "pattern": "hit", "cmd": "x", "hl": {"mode": "match", "color": "#ff0000"}}])
        fired, hl, _ = t.run(["a hit", "", "another hit"])
        self.assertEqual(len(fired), 1)
        self.assertEqual(hl, [(0, 2, 5, "match", "#ff0000"), (2, 8, 11, "match", "#ff0000")])

    def test_disabled_and_bad(self):
        t, _, _ = self.store([{"id": "a", "pattern": "x", "on": False, "cmd": "y"},
                              {"id": "b", "pattern": "([", "regex": True, "cmd": "y"}])
        self.assertEqual(t.run(["x (["])[0], [])

    def test_js_named_group(self):
        t, _, _ = self.store([{"id": "a", "pattern": r"(?<who>\w+) arrives", "regex": True, "cmd": "wave %1"}])
        self.assertEqual(t.run(["Bob arrives"])[0][0][1], "wave Bob")

    def test_save_roundtrip(self):
        t, sent, later = self.store([])
        t.set_list("acct", [{"id": "z", "pattern": "привіт", "cmd": "say hi"}])
        later.run()
        cmd, scope, b64 = sent[-1]
        self.assertEqual((cmd, scope), ("triggers_put", "acct"))
        self.assertEqual(s.b64_decode(b64)["list"][0]["pattern"], "привіт")

    def test_flood(self):
        t, _, _ = self.store([])
        results = [t.allow_command() for _ in range(11)]
        self.assertEqual(results[:10], [True] * 10)
        self.assertEqual(results[10], "paused")
        self.assertFalse(t.allow_command())


class MacroAliasTest(unittest.TestCase):
    def test_macro_lookup_char_first(self):
        m = s.Macros(lambda *a: True, Later())
        m.on_data({"account": True,
                   "char": {"b64": s.b64_encode({"v": 1, "list": [{"key": "f1", "cmd": "c"}]})},
                   "acct": {"b64": s.b64_encode({"v": 1, "list": [{"key": "f1", "cmd": "a"},
                                                                  {"key": "kp2", "cmd": "s"}]})}})
        self.assertEqual(m.command_for("f1"), "c")
        self.assertEqual(m.command_for("kp2"), "s")
        self.assertIsNone(m.command_for("f2"))

    def test_alias_expand(self):
        a = s.Aliases(lambda *x: True, lambda line: True, Later())
        a.on_char({"aliases": [["kk", "kill"]]})
        a.on_acct({"account": True, "b64": s.b64_encode({"v": 1, "list": [
            {"name": "bb", "body": "cast bless|cast armor"}, {"name": "kk", "body": "never"}]})})
        self.assertEqual(a.expand("bb self|kk rat|'bb"), "cast bless|cast armor self|kk rat|'bb")
        self.assertEqual(a.expand("say a||b"), "say a||b")

    def test_char_alias_commands(self):
        sent = []
        a = s.Aliases(lambda *x: True, sent.append, Later())
        a.set_char("old", "new", "a|b")
        self.assertEqual(sent, ["unalias old", "alias new a||b"])

    def test_vars(self):
        self.assertEqual(s.expand_vars("eat $еда and $none", {"еда": "pie"}), "eat pie and $none")

    def test_key_names(self):
        self.assertEqual(s.key_name(112), "f1")
        self.assertEqual(s.key_name(40, "kp2", alt=True), "alt+kp2")
        self.assertEqual(s.key_name(90, None, True, False, True), "ctrl+shift+z")
        self.assertIsNone(s.key_name(16))
        self.assertEqual(s.canonical_key("Shift+Ctrl+я"), "ctrl+shift+z")
        self.assertEqual(s.canonical_key("ctrl+kp+"), "ctrl+kp+")
        self.assertEqual(s.canonical_key("pgdown"), "pgdn")
        self.assertEqual(s.canonical_key("meta+x"), "")


if __name__ == "__main__":
    unittest.main()
