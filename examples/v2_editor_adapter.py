"""v2 adapter contract. Use only public job fields supplied by the runner.

visual_locator_v2: job['images'] = [clean_source, supplied_locator_image].
native_regions_v2: job['images'] = [clean_source]; each unit may contain
region={'point':[x,y]}, {'box':[x1,y1,x2,y2]}, or {'mask':path}.
Ref-only units contain no region. Boxes use half-open integer source pixels.
Pass all unit operations together; preserve the unit/locator association.
Cache the actual model once per process. Record any model-specific resizing
or encoding in the configuration. Return RGB at the original source size.
"""


def edit(*, job: dict, seed: int, config: dict):
    raise NotImplementedError(
        "Connect your model using only job['images'], job['prompt'], and job['units']; "
        "return an RGB PIL.Image at job['source_size']."
    )


def identity_smoke_only(*, job: dict, seed: int, config: dict):
    """Unchanged source for plumbing tests only; this is not an editing model."""
    from PIL import Image

    with Image.open(job["images"][0]) as im:
        return im.convert("RGB")
