"""Render one factual annotation figure from already-public dev requests, CPU only."""

import argparse
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "docs/assets/construction"
SHARED = Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
CASE = "v2-sa_607902"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def fit(im, size, fill="white", nearest=False):
    im = im.copy()
    im.thumbnail(size, Image.Resampling.NEAREST if nearest else Image.Resampling.LANCZOS)
    result = Image.new("RGB", size, fill)
    result.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared", type=Path, default=SHARED)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    shared, output = args.shared, args.output
    output.mkdir(parents=True, exist_ok=True)
    split = json.loads((shared / "plan/splits.json").read_text())
    assert CASE in split["dev"] and CASE not in split["test"]
    public = {}
    proof = []
    for kind in ("mask", "box", "point"):
        path = shared / "requests" / ("S2-" + kind) / CASE / "public.json"
        public[kind] = json.loads(path.read_text())
        proof.append(
            {"path": str(path), "sha256": sha(path), "input_digest": public[kind]["input_digest"]}
        )
    source = public["mask"]["source"]
    assert sha(source["path"]) == source["sha256"]
    image = Image.open(source["path"]).convert("RGB")
    canvas = Image.new("RGB", (1560, 930), "#f7f9fc")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (24, 18),
        "IF-Bench 2.6.0  |  one source, two independent edit units",
        font=font(29, True),
        fill="#142337",
    )
    draw.text(
        (24, 60),
        CASE + "  |  public dev annotation only; no generated edit is shown",
        font=font(20),
        fill="#526277",
    )
    draw.text((24, 106), "Unmodified source image", font=font(23, True), fill="#142337")
    canvas.paste(fit(image, (480, 600)), (24, 148))
    colors = [(0, 128, 150), (201, 95, 30)]
    units = []
    for index, mask_unit in enumerate(public["mask"]["units"]):
        uid = mask_unit["id"]
        box_unit = next(u for u in public["box"]["units"] if u["id"] == uid)
        point_unit = next(u for u in public["point"]["units"] if u["id"] == uid)
        mask_path = mask_unit["region"]["path"]
        assert sha(mask_path) == mask_unit["region"]["sha256"]
        mask = Image.open(mask_path).convert("L")
        arr = np.array(mask) > 0
        ys, xs = np.where(arr)
        box = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
        assert box_unit["region"]["coordinates"] == box
        point = point_unit["region"]["coordinates"]
        assert arr[point[1], point[0]]
        pad = 70 if uid == "U1" else 55
        crop = [
            max(0, box[0] - pad),
            max(0, box[1] - pad),
            min(image.width, box[2] + pad),
            min(image.height, box[3] + pad),
        ]
        overlay = image.copy()
        boundary = np.array(mask.filter(ImageFilter.MaxFilter(7))) > np.array(
            mask.filter(ImageFilter.MinFilter(7))
        )
        pixels = np.array(overlay)
        pixels[boundary] = colors[index]
        overlay = Image.fromarray(pixels)
        d = ImageDraw.Draw(overlay)
        d.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), outline=colors[index], width=3)
        px, py = point
        d.ellipse((px - 6, py - 6, px + 6, py + 6), fill=colors[index], outline="white", width=2)
        x = 534 + index * 510
        draw.text(
            (x, 106),
            uid
            + ("  add: existing rear window" if uid == "U1" else "  remove: existing white SUV"),
            font=font(21, True),
            fill=colors[index],
        )
        canvas.paste(fit(overlay.crop(crop), (486, 270)), (x, 148))
        draw.text(
            (x, 434), "Exact binary source selector (same crop)", font=font(20), fill="#142337"
        )
        canvas.paste(fit(mask.crop(crop), (486, 270), fill="black", nearest=True), (x, 472))
        draw.text((x, 760), "box  " + str(box), font=font(18), fill="#142337")
        draw.text((x, 789), "point  " + str(point), font=font(18), fill="#142337")
        units.append(
            {
                "id": uid,
                "operation": mask_unit["operation"],
                "mask": mask_path,
                "mask_sha256": mask_unit["region"]["sha256"],
                "box": box,
                "point": point,
                "display_crop_xyxy": crop,
            }
        )
    draw.line((24, 835, 1536, 835), fill="#c9d3df", width=2)
    draw.text(
        (24, 851),
        "Mask -> tight half-open box + interior point. The selector identifies existing source pixels.",
        font=font(22),
        fill="#142337",
    )
    draw.text(
        (24, 885),
        "For add, the window is the support anchor; the mask does not prescribe the new decal outline.",
        font=font(21),
        fill="#526277",
    )
    path = output / "annotation_example_v2-sa_607902.png"
    canvas.save(path)
    record = {
        "case_id": CASE,
        "selection": "already-public dev member; no test image opened",
        "split_digest": split["digest"],
        "source": source,
        "public_requests": proof,
        "units": units,
        "image": path.name,
        "image_sha256": sha(path),
        "image_size": list(canvas.size),
        "inference_calls": 0,
        "code_sha256": sha(__file__),
    }
    (output / "annotation_example_provenance.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({"path": str(path), "sha256": record["image_sha256"], "source_case": CASE}))


if __name__ == "__main__":
    main()
