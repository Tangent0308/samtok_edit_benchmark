"""Selection extension must preserve previous cases and never duplicate a request."""
import unittest

from samtok_benchmark.external_pilot.extension import extend_groups
from samtok_benchmark.external_pilot.extension_report import aggregate, current_notes


class ExtensionTests(unittest.TestCase):
    def test_preserves_previous_and_is_deterministic(self):
        groups = {"a": list(range(10)), "b": list(range(10, 20))}
        result = extend_groups(groups, [2, 14], {"a": 3, "b": 3}, lambda x: x)
        self.assertEqual(result, extend_groups(groups, [2, 14], {"a": 3, "b": 3}, lambda x: x))
        self.assertEqual(len(set(result)), 6)
        self.assertTrue({2, 14}.issubset(result))
        self.assertEqual(sum(x < 10 for x in result), 3)

    def test_missing_prior_or_undersized_quota_is_rejected(self):
        for prior, quota in [([99], 2), ([1, 2], 1), ([], 4)]:
            with self.assertRaises(ValueError):
                extend_groups({"a": [1, 2, 3]}, prior, {"a": quota}, lambda x: x)

    def test_combined_mean_uses_cases_not_equal_weighted_batch_means(self):
        cases = [{"metrics": {"score": x}} for x in (0, 1, 1, 1)]
        result = aggregate(cases, {"score": "score"}, {})["score"]
        self.assertEqual(result["mean"], .75)
        self.assertTrue(result["complete"])

    def test_native_area_weights_and_missing_are_preserved(self):
        cases = [{"metrics": {"score": 0, "area": 3}}, {"metrics": {"score": 1, "area": 1}}, {"metrics": {}}]
        result = aggregate(cases, {"score": "score"}, {"score": "area"})["score"]
        self.assertEqual(result["mean"], .25)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total"], 3)
        self.assertFalse(result["complete"])

    def test_scope_notes_follow_new_selection(self):
        selection = {"total": 24, "selected": [{"case_id": f"{kind}-{i:04d}-k{k}"}
                     for kind in ("real", "syn") for i in range(3) for k in (1, 2, 4, 8)]}
        note = current_notes("complex_edit", selection, ["real/syn 各 1 张原图；不是 8 张独立源图。"])[0]
        self.assertIn("real 3 张、syn 3 张", note)
        self.assertIn("24 条请求、6 张独立源图", note)
        selection = {"selected": [{"task_type": str(i)} for i in range(11) for _ in range(2)]}
        note = current_notes("gedit", selection, ["英文 11 类各 1 条，使用原始指令。"])[0]
        self.assertIn("11 类各 2 条", note)


if __name__ == "__main__":
    unittest.main()
