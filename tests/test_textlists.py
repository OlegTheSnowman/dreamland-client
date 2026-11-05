import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dlclient import textlists as T


class TextListTest(unittest.TestCase):
    def test_no_text_parsers(self):
        for kind, (command, parser, title, keys) in T.PARSERS.items():
            self.assertIsNone(parser, kind)
            self.assertTrue(command and title and keys, kind)

    def test_pager(self):
        self.assertTrue(T.is_pager("[Press Enter to continue]"))
        self.assertTrue(T.is_pager("Натисни Enter, щоб продовжити"))
        self.assertFalse(T.is_pager("You say 'enter'"))


if __name__ == "__main__":
    unittest.main()
