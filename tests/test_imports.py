import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ImportTest(unittest.TestCase):
    def test_every_module_loads(self):
        import importlib
        import pkgutil
        import dlclient
        for mod in pkgutil.iter_modules(dlclient.__path__):
            importlib.import_module("dlclient." + mod.name)


if __name__ == "__main__":
    unittest.main()
