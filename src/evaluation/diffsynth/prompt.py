"""One editing prompt for every model; only the image names follow each model's template.

Qwen-Image-Edit-2511 prefixes its inputs with "Picture 1:", "Picture 2:"; Qwen-Image-2.1 inserts
<image1>, <image2>; FLUX.2 [dev] is prompted with "image 1", "image 2" (BFL multi-reference guide).
Unit instructions are copied verbatim from the public job.
"""

from __future__ import annotations

PROMPT_VERSION = "two_image_locator_prompt_v1"

# Same order as samtok_benchmark.v2.inputs.COLORS, which renders U1..U5.
COLOR_NAMES = ("red", "blue", "gold", "purple", "green")
MARKERS = {
    "point": "{color} dot labeled {uid}",
    "box": "{color} rectangle labeled {uid}",
    "mask": "{color} translucent highlighted region labeled {uid}",
}
IMAGE_NAMES = {"picture": ("Picture 1", "Picture 2"), "image": ("Image 1", "Image 2")}


def build_prompt(job: dict, image_names: str) -> str:
    source, locator = IMAGE_NAMES[image_names]
    # The mask pilot stores its prompt in the public job with a sentinel so that the
    # full visual-locator benchmark keeps its original prompt and run behavior.  Only
    # placeholder substitution depends on the model-specific image naming convention.
    pilot_prompt = job.get("prompt", "")
    if pilot_prompt.startswith(("[SAMTOK_MASK_PILOT_V1]", "[SAMTOK_LABEL_MAP_V1]")):
        return pilot_prompt.replace("{SOURCE}", source).replace("{REGION}", locator)
    has_locator = len(job["images"]) == 2
    if has_locator:
        intro = (
            f"{source} is the photo to edit. {locator} is the same photo with colored, labeled "
            f"markers that only indicate targets. Edit {source} and output the complete edited "
            "photo without any markers. "
        )
    else:
        intro = f"Edit {source} and output the complete edited photo. "
    intro += (
        "Perform all instructions together and keep everything else unchanged. "
        "A marker selects an existing object; a named part restricts the edit to that part. "
        'For "Add", the marker shows the existing object the new item attaches to.'
    )
    lines = []
    for unit in job["units"]:
        uid = unit["id"]
        if unit["locator"] == "none":
            where = "no marker; identify it from the description"
        else:
            color = COLOR_NAMES[int(uid[1:]) - 1]
            where = MARKERS[unit["locator"]].format(color=color, uid=uid) + f" in {locator}"
        lines.append(f"{uid} ({where}): {unit['instruction']}")
    return intro + "\n\n" + "\n".join(lines)


def build_single_image_locator_prompt(job: dict) -> str:
    """Build the fixed prompt used by models whose official editor takes one image.

    The only image passed to those pipelines is the visual-locator image when a locator
    exists.  Keeping this wording separate makes that adapter choice explicit in the run
    configuration instead of silently pretending the model received two images.
    """
    if len(job["images"]) == 2:
        intro = (
            "The input image is the photo to edit with colored, labeled markers overlaid. "
            "The markers are spatial selectors only. Edit the underlying photo and output the "
            "complete edited photo. Do not copy, render, preserve, or mention any marker, "
            "color, rectangle, mask, point, or U-label. "
        )
    else:
        intro = "Edit the input photo and output the complete edited photo. "
    intro += (
        "Perform all instructions together and keep everything else unchanged. "
        "A marker selects an existing object; a named part restricts the edit to that part. "
        'For "Add", the marker shows the existing object the new item attaches to.'
    )
    lines = []
    for unit in job["units"]:
        uid = unit["id"]
        if len(job["images"]) == 2 and unit["locator"] != "none":
            color = COLOR_NAMES[int(uid[1:]) - 1]
            where = MARKERS[unit["locator"]].format(color=color, uid=uid)
        else:
            where = "no marker; identify it from the description"
        lines.append(f"{uid} ({where}): {unit['instruction']}")
    return intro + "\n\n" + "\n".join(lines)
