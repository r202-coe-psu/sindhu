"""Test packages must not share a name with a brython package.

Tests run with ``unittest discover -s tests -t tests``, so every folder under
tests/ is a top-level package. Several tests put the brython root on sys.path
to import ``maps``, ``stations`` and so on; a test package of the same name
shadows one side, depending on sys.path order.
"""

import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
BRYTHON_ROOT = TESTS.parent / "sindhu" / "web" / "static" / "brython"


def _packages(root):
    return {
        path.parent.name
        for path in root.glob("*/__init__.py")
        if path.parent.name != "__pycache__"
    }


class PackageNameTests(unittest.TestCase):
    def test_brython_packages_are_found(self):
        self.assertIn("maps", _packages(BRYTHON_ROOT))

    def test_test_packages_do_not_shadow_brython_packages(self):
        self.assertEqual(_packages(TESTS) & _packages(BRYTHON_ROOT), set())


if __name__ == "__main__":
    unittest.main()
