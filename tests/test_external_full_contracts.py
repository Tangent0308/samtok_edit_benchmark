"""CPU contracts for sequential inputs, model isolation and official macro aggregation."""

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from samtok_benchmark.external_full.data import identity, resolve_input
from samtok_benchmark.external_full.launch import select_cases
from samtok_benchmark.external_full.report import aggregate
from samtok_benchmark.external_full.worker import scientific_config, verify_config
from samtok_benchmark.external_full.judge import messages, parse
from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file


class SequentialInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "sitedit"
        self.item = {
            "case_id": "second",
            "parent_case_id": "first",
            "turn": 2,
            "instruction": "Remove the blue object.",
            "sequence_id": "chain",
        }

    def tearDown(self):
        self.temp.cleanup()

    def parent(self, status="completed", model="sitedit"):
        path = self.root / "edit/first"
        path.mkdir(parents=True)
        Image.new("RGB", (640, 640), (32, 64, 96)).save(path / "output.png")
        receipt = {
            "identity": {"case_id": "first", "model": model},
            "status": status,
            "output_image": str(path / "output.png"),
            "output_sha256": sha256_file(path / "output.png"),
            "output_size": [640, 640],
        }
        immutable(path / "result.json", receipt)
        return receipt

    def test_waiting_never_substitutes_gt(self):
        resolved, _, state = resolve_input(self.item, self.root)
        self.assertEqual(state, "waiting_parent")
        self.assertIsNone(resolved)
        self.assertFalse((self.root / "inputs").exists())

    def test_failed_parent_does_not_make_input(self):
        self.parent("failed")
        _, binding, state = resolve_input(self.item, self.root)
        self.assertEqual(state, "failed_parent")
        self.assertEqual(binding["case_id"], "first")
        self.assertFalse((self.root / "inputs").exists())

    def test_generated_pixels_are_the_only_turn2_input(self):
        parent = self.parent()
        resolved, binding, state = resolve_input(self.item, self.root, {"model": "sitedit"})
        self.assertIsNone(state)
        public = read(resolved["public"])
        self.assertEqual(public["instruction"], self.item["instruction"])
        self.assertEqual(public["source"]["size"], [1024, 1024])
        with Image.open(public["source"]["path"]) as image:
            self.assertEqual(image.getpixel((512, 512)), (32, 64, 96))
        self.assertEqual(binding["output_sha256"], parent["output_sha256"])
        self.assertNotIn("mask", public)
        self.assertNotIn("target", public)
        self.assertEqual(resolve_input(self.item, self.root)[0], resolved)

    def test_changed_parent_and_cross_model_receipt_rejected(self):
        self.parent(model="qwen21")
        with self.assertRaisesRegex(ValueError, "identity differs"):
            resolve_input(self.item, self.root, {"model": "sitedit"})
        Image.new("RGB", (640, 640), "red").save(self.root / "edit/first/output.png")
        with self.assertRaisesRegex(ValueError, "output modified"):
            resolve_input(self.item, self.root)


class ProtocolTests(unittest.TestCase):
    def test_vlm_evidence_contains_two_images_and_no_method_filename(self):
        import base64
        import json

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            output = Path(directory) / "qwen21-output.png"
            Image.new("RGB", (8, 8), "red").save(source)
            Image.new("RGB", (8, 8), "blue").save(output)
            evidence = messages(
                "Official template.", "Move the object left.", str(source), str(output)
            )
            encoded = json.dumps(evidence)
            self.assertNotIn("qwen21", encoded)
            images = [x for x in evidence[0]["content"] if x["type"] == "image_url"]
            self.assertEqual(len(images), 2)
            for item, path in zip(images, (source, output)):
                self.assertEqual(
                    base64.b64decode(item["image_url"]["url"].split(",", 1)[1]), path.read_bytes()
                )

    def test_vlm_parser_keeps_zero_and_rejects_out_of_range_or_boolean(self):
        self.assertEqual(parse('{"score":0,"reason":"Unchanged"}')["score"], 0)
        self.assertEqual(parse('```json\n{"score":7.5,"reason":"Partial"}\n```')["score"], 7.5)
        for text in (
            '{"score":true,"reason":"x"}',
            '{"score":11,"reason":"x"}',
            '{"score":7,"reason":""}',
            '{"score":NaN,"reason":"x"}',
        ):
            with self.assertRaises(ValueError):
                parse(text)

    def test_turn_ids_group_but_never_collide(self):
        first = identity("multi_turn_add", "turn1_add/a_t1.png")
        second = identity("multi_turn_add", "turn2_add/a_t1.png")
        alternate = identity("multi_turn_add", "turn1_add/a_t2.png")
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(first[1], second[1])
        self.assertNotEqual(first[1], alternate[1])
        self.assertEqual((first[2], second[2]), (1, 2))

    def test_selection_is_closed_over_previous_turn(self):
        cases = [{"case_id": "a", "parent_case_id": None}, {"case_id": "b", "parent_case_id": "a"}]
        self.assertEqual(select_cases({"cases": cases}, ["b"]), cases)
        with self.assertRaises(ValueError):
            select_cases({"cases": cases}, ["unknown"])

    def test_official_macro_not_size_weighted(self):
        rows = [
            {
                "task": task,
                "expected": count,
                "scored": count,
                "complete": True,
                "valid_mean": {key: value for key in ("LC-T", "LC-I", "PSNR", "SSIM", "LPIPS")},
            }
            for task, count, value in [("add", 982, 1), ("remove", 1331, 3), ("replace", 152, 8)]
        ]
        result = aggregate(rows)[0]
        self.assertEqual(result["valid_mean"]["LC-T"], 4)
        self.assertEqual(result["expected"], 2465)
        rows[0]["complete"] = False
        self.assertFalse(aggregate(rows)[0]["complete"])

    def test_partial_category_does_not_claim_full_macro(self):
        rows = [
            {
                "task": "add",
                "expected": 1,
                "scored": 1,
                "complete": True,
                "valid_mean": {key: 1 for key in ("LC-T", "LC-I", "PSNR", "SSIM", "LPIPS")},
            }
        ]
        result = aggregate(rows)[0]
        self.assertFalse(result["complete"])
        self.assertIsNone(result["valid_mean"]["LC-T"])

    def test_runtime_paths_do_not_invalidate_scientific_configuration(self):
        cfg = {"seed": 42, "sitedit": {"gamma": 2}, "model_specifications": {}, "benchmark": {}}
        self.assertEqual(
            scientific_config(cfg), scientific_config({**cfg, "runtime": {"v4": "new"}})
        )
        self.assertNotEqual(scientific_config(cfg), scientific_config({**cfg, "seed": 43}))

    def test_full_config_preserves_frozen_sitedit_row(self):
        config = read(next((Path(__file__).parents[1] / "configs/external").glob("*_full4.json")))
        verify_config(config)
        self.assertEqual(config["model_specifications"]["mirage"]["parameters"]["patch_ratio"], 0.4)


if __name__ == "__main__":
    unittest.main()
