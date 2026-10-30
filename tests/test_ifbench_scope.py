from samtok_benchmark.ifbench.dev_scope import project


def test_deferral_excludes_tasks_aliases_selection_without_changing_registration():
    plan = {
        "digest": "original",
        "tasks": [{"model": "maskflow"}, {"model": "qwen2511"}],
        "aliases": [{"model": "maskflow"}, {"model": "qwen2511"}],
        "candidates": {"maskflow": [], "qwen2511": []},
        "selection": {"settings": {"maskflow": ["S2-mask"], "qwen2511": ["S1"]}},
    }
    scope = {"base_plan_digest": "original", "excluded_models": ["maskflow"]}
    active = project(plan, scope)
    assert active["tasks"] == [{"model": "qwen2511"}]
    assert active["aliases"] == [{"model": "qwen2511"}]
    assert set(active["candidates"]) == {"qwen2511"}
    assert set(active["selection"]["settings"]) == {"qwen2511"}
    assert active["digest"] == plan["digest"] == "original"
    assert len(plan["tasks"]) == 2
