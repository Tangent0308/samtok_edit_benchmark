import copy
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest
from PIL import Image

from samtok_benchmark.io import sha256_file, write_jsonl
from samtok_benchmark.v2.review import package_review
from test_v2 import v2release as v2release


@pytest.fixture
def review_package(v2release, tmp_path):
    root, manifest, case = v2release
    second = copy.deepcopy(case)
    second["id"] = "v2-synthetic-two"
    second["source"]["family_id"] = "synthetic-two"
    source = root / "second.png"
    Image.new("RGB", (160, 120), "black").save(source)
    second["source"].update(image=source.name, sha256=sha256_file(source))
    second["review"].update(card=source.name, card_sha256=sha256_file(source))
    write_jsonl(manifest, [case, second])
    out = tmp_path / "review"
    metadata = package_review(manifest, root, out)
    spec = importlib.util.spec_from_file_location("isolated_v2_review", out / "run_review.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    return out, metadata, server


def payload(meta, cid="v2-synthetic"):
    return {
        "case_id": cid,
        "manifest_sha256": meta["manifest_sha256"],
        "decision": "accept",
        "reviewer": "SYNTHETIC_TEST_ONLY",
        "note": "Not an actual human review.",
        "view_modes": {"U1": "none", "U2": "point", "U3": "box", "U4": "mask"},
        "unit_notes": {"U2": "Test note"},
        "instruction_suggestions": {},
    }


def test_review_package_is_standalone_and_case_metadata_is_lazy(review_package):
    out, meta, _ = review_package
    assert meta["cases"] == 2 and meta["lazy_case_assets"]
    index = json.loads((out / "cases.json").read_text())
    assert all("units" not in c and "source" not in c for c in index)
    assert not (out / ".git").exists()
    for c in index:
        row = json.loads((out / "cases" / f"{c['id']}.json").read_text())
        assert (out / row["source"]["image"]).exists()
        assert (out / row["formal_input_image"]).exists()
        assert all((out / u["target"]["mask"]).exists() for u in row["units"])
    first = json.loads((out / "cases/v2-synthetic.json").read_text())
    second = json.loads((out / "cases/v2-synthetic-two.json").read_text())
    assert first["formal_input_image"] != second["formal_input_image"]
    assert "None" not in first["public_units"][0]["instruction"]
    assert first["public_units"][1]["instruction"] == "Recolor both legs blue."
    with pytest.raises(FileExistsError):
        package_review(out / "benchmark/cases.jsonl", out, out)


def test_review_suggestions_persist_without_changing_frozen_manifest(review_package):
    out, meta, server = review_package
    before = sha256_file(out / "benchmark/cases.jsonl")
    request = payload(meta)
    request["instruction_suggestions"] = {"U2": "Suggested alternative."}
    record = server.save_record(request)
    assert record["review_kind"] == "user_entered_unverified_identity"
    assert (
        server.load_reviews()["cases"]["v2-synthetic"]["instruction_suggestions"]["U2"]
        == "Suggested alternative."
    )
    assert sha256_file(out / "benchmark/cases.jsonl") == before
    assert not list((out / "reviews").glob("*.tmp"))


@pytest.mark.parametrize("bad", ["manifest", "case", "unit", "mode", "identity"])
def test_review_rejects_mismatched_or_incomplete_records(review_package, bad):
    out, meta, server = review_package
    request = payload(meta)
    if bad == "manifest":
        request["manifest_sha256"] = "changed"
    elif bad == "case":
        request["case_id"] = "../not-a-case"
    elif bad == "unit":
        request["unit_notes"] = {"unknown": "oops"}
    elif bad == "mode":
        request["view_modes"] = {"U1": "invalid"}
    else:
        request["reviewer"] = ""
    with pytest.raises(ValueError):
        server.save_record(request)
    assert not (out / "reviews/review_results.json").exists()


def test_http_saves_merge_cases_and_export_on_restart(review_package):
    out, meta, module = review_package
    http = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{http.server_address[1]}"
    try:
        for cid in ["v2-synthetic", "v2-synthetic-two"]:
            request = Request(
                base + "/api/review",
                data=json.dumps(payload(meta, cid)).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request) as response:
                assert json.load(response)["ok"]
        with urlopen(base + "/api/export") as response:
            assert "attachment" in response.headers["Content-Disposition"]
            result = json.load(response)
        assert set(result["cases"]) == {"v2-synthetic", "v2-synthetic-two"}
        assert set(module.load_reviews()["cases"]) == set(result["cases"])
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


def test_independent_overlay_flags_persist_and_reject_unknown_layers(review_package):
    _, meta, server = review_package
    request = payload(meta)
    request["overlay_flags"] = {"U1": {"mask": True, "box": True, "ref": True}}
    record = server.save_record(request)
    assert record["overlay_flags"] == request["overlay_flags"]
    request["overlay_flags"]["U1"]["private"] = True
    with pytest.raises(ValueError, match="overlay"):
        server.save_record(request)
