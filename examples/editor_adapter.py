"""Example integration contract; replace the body with your model's inference.

    samtok-benchmark run-editor --inputs outputs/inputs/inputs.jsonl \
        --adapter examples.editor_adapter:edit --method my_model \
        --adapter-config examples/editor_config.json --output outputs/my_model

The adapter must use the images/prompt in job unchanged. Visual-locator jobs
use [clean source, locator]; text-only jobs contain only a clean source.
Native-region jobs expose only the selected modality in job['controls'].
Return RGB at job['source_size']; report any native-size resampling in config.
Load and cache your model once at module/process level rather than per case.
"""


def edit(*, job: dict, seed: int, config: dict):
    raise NotImplementedError(
        "Implement your model here using job['images'], job['prompt'], "
        "job['controls'], and the supplied seed. Return an RGB PIL.Image."
    )
