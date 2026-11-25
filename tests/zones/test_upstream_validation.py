import unittest

from sindhu.services.zones import upstream_violation


class UpstreamViolationTests(unittest.TestCase):
    def test_accepts_a_valid_chain(self):
        graph = {"a": [], "b": ["a"], "c": ["b"]}

        self.assertIsNone(upstream_violation("c", ["b"], graph))
        self.assertIsNone(upstream_violation("c", ["a", "b"], graph))

    def test_accepts_empty_upstream(self):
        self.assertIsNone(upstream_violation("a", [], {"a": ["b"], "b": []}))

    def test_rejects_zone_as_its_own_upstream(self):
        message = upstream_violation("a", ["a"], {"a": []})

        self.assertIn("ตัวเอง", message)

    def test_rejects_cycle_of_two(self):
        graph = {"a": [], "b": ["a"]}

        message = upstream_violation("a", ["b"], graph)

        self.assertIn("วงวน", message)

    def test_rejects_cycle_of_three(self):
        graph = {"a": [], "b": ["a"], "c": ["b"]}

        message = upstream_violation("a", ["c"], graph)

        self.assertIn("วงวน", message)

    def test_cycle_is_found_beyond_the_first_level(self):
        graph = {"a": [], "b": ["a"], "c": ["b"], "d": []}

        self.assertIsNotNone(upstream_violation("a", ["d", "c"], graph))

    def test_diamond_without_a_cycle_is_valid(self):
        graph = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"]}

        self.assertIsNone(upstream_violation("e", ["d"], {**graph, "e": []}))

    def test_replacing_the_zones_own_edges_removes_the_cycle(self):
        graph = {"a": ["b"], "b": []}

        self.assertIsNone(upstream_violation("a", [], graph))
        self.assertIsNone(upstream_violation("b", [], graph))

    def test_rejects_unknown_deleted_or_reference_zone_id(self):
        graph = {"a": []}

        message = upstream_violation("b", ["ghost"], {**graph, "b": []})

        self.assertIn("ไม่พบโซนต้นน้ำ", message)

    def test_create_without_zone_id_checks_existence_only(self):
        graph = {"a": [], "b": ["a"]}

        self.assertIsNone(upstream_violation(None, ["a", "b"], graph))
        self.assertIsNotNone(upstream_violation(None, ["ghost"], graph))


if __name__ == "__main__":
    unittest.main()
