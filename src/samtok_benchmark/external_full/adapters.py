"""Frozen native methods with explicit benchmark public-input routing."""

from samtok_benchmark.external_refedit import adapters as text
from . import mask_adapters


def build(model, stage, config, root):
    if config["benchmark"]["id"] == "interedit":
        return mask_adapters.build(model, stage, config, root)
    return text.build(model, stage, config, root)
