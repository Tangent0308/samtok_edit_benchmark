"""Full CompBench release: public-only editing, autoregressive turns and official metrics."""

from samtok_benchmark.external_refedit import MODELS

REVISION = "a4c5a4d1854056d24aad43a494772dc90588d426"
COUNTS = {"add": 982, "remove": 1331, "replace": 152, "implicit_reasoning": 100,
          "multi_object_add": 72, "multi_object_remove": 72,
          "multi_turn_add": 288, "multi_turn_remove": 288,
          "action": 89, "location": 73, "view": 34}
VLM_TASKS = ("action", "location", "view")

__all__ = ["MODELS", "REVISION", "COUNTS", "VLM_TASKS"]
