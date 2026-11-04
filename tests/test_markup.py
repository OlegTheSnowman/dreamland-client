import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dlclient.markup import OutputParser
from dlclient.telnet import Telnet, IAC, WILL, WONT, ECHO

HERE = os.path.dirname(os.path.abspath(__file__))


def frames():
    with open(os.path.join(HERE, "login_frames.txt"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("{"):
                yield json.loads(line)


class ParserTest(unittest.TestCase):
    def setUp(self):
        self.p = OutputParser()
        self.p.nonce = "ABCDEFGH"

    def parse(self, s):
        return self.p.parse(s)

    def test_language_menu_from_server(self):
        menu = [f for f in frames() if "Choose your language" in str(f["args"])][0]
        lines, complete, msp = self.parse(menu["args"][0])
        text = "\n".join(l.text for l in lines)
        self.assertIn("Welcome to Dreamland! Choose your language:", text)
        self.assertNotIn("<", text.replace("&lt;", ""))
        cmds = [l.command for line in lines for l in line.links]
        self.assertEqual(cmds, ["english", "українська", "русский"])
        line = [l for l in lines if "english" in l.text][0]
        link = line.links[0]
        self.assertEqual(line.text[link.start:link.end], "english")
        self.assertFalse(complete)

    def test_entities_and_colour(self):
        lines, complete, _ = self.parse("<c c='fgbr'>&gt;</c> a &amp; b &lt;x&gt;\n")
        self.assertEqual(lines[0].text, "> a & b <x>")
        self.assertTrue(complete)

    def test_hc_cmd_allowlist(self):
        lines, _, _ = self.parse("<hc cmd='path 3001'>Market</hc> <hc cmd='give all.coins Vasya'>Trap</hc>")
        a, b = lines[0].links
        self.assertEqual(a.command, "path 3001")
        self.assertEqual(b.command, "Trap")

    def test_help_group_speedwalk_web(self):
        lines, _, _ = self.parse("<hh id='12'>  fire </hh><hg>attack</hg><hs>2n3e</hs><hl>https://x.y</hl><hl>ftp://no</hl>")
        cmds = [(l.label, l.command, l.url) for l in lines[0].links]
        self.assertEqual(cmds, [("fire", "help 12", ""), ("attack", "glist attack", ""),
                                ("2n3e", "run 2n3e", ""), ("https://x.y", "", "https://x.y")])
        fire = lines[0].links[0]
        self.assertEqual(lines[0].text[fire.start:fire.end], "fire")

    def test_item_menu(self):
        lines, _, _ = self.parse("<m i='123456' c='take $,wear $' l='sell $'>a sword</m>")
        link = lines[0].links[0]
        self.assertEqual(link.label, "a sword")
        self.assertEqual(link.menu, [("take", "take 123456"), ("wear", "wear 123456"), None,
                                     ("sell", "sell 123456")])

    def test_brackets(self):
        lines, _, _ = self.parse("A [read=sign знак,see=sign] and [look=door,see=door]. "
                                 "[cmd=quest $1,see= info ,nonce=ABCDEFGH] "
                                 "[cmd=give all,see=bad,nonce=XXXXXXXX]")
        line = lines[0]
        self.assertEqual([l.command for l in line.links], ["examine 'sign знак'", "look door", "quest info"])
        self.assertIn("[cmd=give all,see=bad,nonce=XXXXXXXX]", line.text)
        self.assertTrue(line.text.startswith("A sign and door."))

    def test_msp_only_when_enabled(self):
        lines, _, msp = self.parse("!!SOUND(combat/hit V=50 P=60)\nhi\n")
        self.assertEqual(msp, [])
        self.p.msp_enabled = True
        lines, _, msp = self.parse("!!SOUND(combat/hit V=50 P=60)\nhi\n")
        self.assertEqual(msp, [("sound", "combat/hit", {"V": "50", "P": "60"})])
        self.assertEqual([l.text for l in lines], ["hi"])

    def test_ansi_stripped(self):
        lines, _, _ = self.parse("\r\n\x1b[0;0H\x1b[2Jhello\r\n")
        self.assertEqual([l.text for l in lines], ["", "hello"])


class ColourExitsTest(unittest.TestCase):
    def test_colour_spans_per_line(self):
        p = OutputParser()
        lines, _, _ = p.parse("hi <c c='fgbr'>red\nmore</c> x\n")
        self.assertEqual([(l.text[a:b], c) for l in lines for a, b, c in l.colors], [("red", "fgbr"), ("more", "fgbr")])


class UpdaterTest(unittest.TestCase):
    def test_versions(self):
        from dlclient.updater import is_newer, parse_version
        self.assertEqual(parse_version("v1.2"), (1, 2, 0))
        self.assertTrue(is_newer("v1.0.1", "1.0.0"))
        self.assertFalse(is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(is_newer("0.9.9", "1.0.0"))


class TelnetTest(unittest.TestCase):
    def test_echo_and_literal_iac(self):
        t = Telnet()
        self.assertEqual(t.process("Password: " + IAC + WILL + ECHO), "Password: ")
        self.assertTrue(t.echo_off)
        self.assertEqual(t.process(IAC + WONT), "")
        self.assertEqual(t.process(ECHO + "ok " + IAC + IAC), "ok " + IAC)
        self.assertFalse(t.echo_off)


if __name__ == "__main__":
    unittest.main()
