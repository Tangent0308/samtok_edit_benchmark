#!/usr/bin/env python3
"""Render fixed, output-independent MagicBrush comparisons from immutable real records."""

import argparse
import hashlib
import json
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont


NAMES = {
    "sitedit": "SITEdit",
    "qwen21": "Qwen-Image-2.1",
    "qwen2511": "Qwen-Image-Edit-2511",
    "replan": "RePlan",
    "mirage": "MIRAGE",
    "flux3": "FLUX.3 Klein",
    "mice": "MICE",
    "flux2_klein9b": "FLUX.2 Klein-9B",
}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        raise ValueError("Use a new destination; existing images are never overwritten")
    plan, report, selection = read(args.run / "RUN.json"), read(args.report), read(args.selection)
    if report["schema"] != "magicbrush.failure-inclusive-report.v1" or not report["complete"]:
        raise ValueError("Requires the completed, verified failure-inclusive report")
    plan_digest = hashlib.sha256(
        json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    if report["run_digest"] != plan_digest:
        raise ValueError("Report belongs to a different generation plan")
    original = args.run / "report/REPORT.json"
    if (
        original.resolve() != Path(report["original_report"]["path"]).resolve()
        or sha(original) != report["original_report"]["sha256"]
    ):
        raise ValueError("Original final report binding changed")
    bundle = Path(plan["bundle"])
    index = read(bundle / "index.json")
    if (
        index["digest"] != selection["bundle_digest"]
        or sha(bundle / "index.json") != selection["index_sha256"]
    ):
        raise ValueError("Selection belongs to a different input bundle")
    private = {c["case_id"]: c for c in read(bundle / "private/evaluation.json")}
    if sha(bundle / "private/evaluation.json") != index["evaluation_sha256"]:
        raise ValueError("Reference annotations changed")
    public_hashes = {c["public"]: c["public_sha256"] for c in index["cases"]}
    scores = {}
    for row in report["rows"]:
        if row["subset"] == "full":
            for case in row["per_case"]:
                key = row["model"], case["key"]
                if key in scores and scores[key] != case:
                    raise ValueError("Conflicting shared first-turn score")
                scores[key] = case
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font = ImageFont.truetype(font_path, 16)
    heading = ImageFont.truetype(font_path, 20)
    small = ImageFont.truetype(font_path, 13)
    side, gap, margin = 256, 16, 20
    width = 4 * (side + gap) + 2 * margin - gap
    provenance, figures = [], []
    args.destination.mkdir(parents=True, exist_ok=False)

    def checked(path, expected, role):
        path = Path(path)
        actual = sha(path)
        if actual != expected:
            raise ValueError(f"Changed {role}: {path}")
        with Image.open(path) as image:
            image.load()
            rgb = image.convert("RGB")
        provenance.append(
            {"path": str(path), "sha256": actual, "role": role, "size": list(rgb.size)}
        )
        return rgb

    def panel(canvas, x, y, image, title):
        draw = ImageDraw.Draw(canvas)
        draw.text((x, y), title, font=font, fill="#182337")
        y += 24
        draw.rectangle((x, y, x + side - 1, y + side - 1), fill="#f1f3f5", outline="#ccd2da")
        if image is not None:
            image = image.copy()
            image.thumbnail((side, side), Image.Resampling.LANCZOS)
            canvas.paste(image, (x + (side - image.width) // 2, y + (side - image.height) // 2))
        else:
            draw.text((x + 18, y + side // 2 - 10), "No generated image", font=font, fill="#a13d34")

    for session in selection["sessions"]:
        case = session["cases"][-1]
        cid = case["case_id"]
        for track in ("mask-free", "mask-provided"):
            for mode in ["independent", "iterative"] if session["turns"] > 1 else ["independent"]:
                public_path = bundle / "public" / track / cid / "public.json"
                if sha(public_path) != public_hashes[str(public_path)]:
                    raise ValueError("Public request changed")
                public = read(public_path)
                key = f"{track}/{mode}/{cid}"
                instructions = [f"Turn {c['turn']}: {c['instruction']}" for c in session["cases"]]
                lines = [line for text in instructions for line in textwrap.wrap(text, width=108)]
                header_height = 88 + 23 * len(lines)
                context_height = side + 58
                block_height = 2 * (side + 24) + 98
                canvas = Image.new(
                    "RGB", (width, header_height + context_height + 2 * block_height + 30), "white"
                )
                draw = ImageDraw.Draw(canvas)
                draw.text(
                    (margin, 14),
                    f"MagicBrush | {cid} | {track} | {mode}",
                    font=heading,
                    fill="#182337",
                )
                for n, line in enumerate(lines):
                    draw.text((margin, 46 + 23 * n), line, font=font, fill="#344158")
                draw.text(
                    (margin, header_height - 24),
                    "Fixed selection; all methods shown. Reference image is for evaluation/display only.",
                    font=small,
                    fill="#596579",
                )
                source = checked(
                    public["source"]["path"],
                    public["source"]["sha256"],
                    "public independent source",
                )
                truth = private[cid]["target"]
                target = checked(truth["path"], truth["sha256"], "evaluation reference")
                panel(canvas, margin, header_height, source, "Dataset source for this turn")
                panel(canvas, margin + side + gap, header_height, target, "Reference target (GT)")
                if public.get("mask"):
                    mask = checked(
                        public["mask"]["path"], public["mask"]["sha256"], "public edit mask"
                    )
                    panel(
                        canvas,
                        margin + 2 * (side + gap),
                        header_height,
                        mask,
                        "Public mask (white = edit)",
                    )
                note_x = margin + 3 * (side + gap)
                notes = "Each method's actual clean editing input is shown above its output. Regional conditioning follows its frozen adapter. Iterative inputs are method-specific preceding outputs. No image cleanup."
                for n, line in enumerate(textwrap.wrap(notes, width=29)):
                    draw.text(
                        (note_x, header_height + 30 + n * 21), line, font=font, fill="#596579"
                    )
                for n, (model, name) in enumerate(NAMES.items()):
                    path = args.run / "runs" / model / "edit" / key / "result.json"
                    result = read(path)
                    identity = result["identity"]
                    if (
                        identity["source_code"] != plan["source_code"]
                        or identity["bundle_digest"] != plan["bundle_digest"]
                        or identity["config_digest"] != plan["config_digest"]
                    ):
                        raise ValueError(f"Generation identity mismatch: {path}")
                    provenance.append(
                        {"path": str(path), "sha256": sha(path), "role": "generation receipt"}
                    )
                    call_path = path.parent / "call.json"
                    actual_input, output = None, None
                    if call_path.exists():
                        call = read(call_path)
                        actual_public = (
                            public
                            if mode == "independent"
                            else read(args.run / "public_recurrent" / model / key / "public.json")
                        )
                        if actual_public["input_digest"] != identity["public_digest"]:
                            raise ValueError("Actual public request does not match generation")
                        source_spec = actual_public["source"]
                        if "source" in call:
                            recorded = call["source"]
                        elif model == "sitedit":
                            recorded = call["images"][0]
                        elif model in ("mirage", "mice"):
                            recorded = {"path": call["image"], "sha256": source_spec["sha256"]}
                        else:
                            raise ValueError(f"Unknown actual-input schema for {model}")
                        if (
                            Path(recorded["path"]).resolve() != Path(source_spec["path"]).resolve()
                            or recorded["sha256"] != source_spec["sha256"]
                        ):
                            raise ValueError("Call input disagrees with its bound public source")
                        actual_input = checked(
                            source_spec["path"],
                            source_spec["sha256"],
                            f"{model} actual clean editing input",
                        )
                        if model == "mice":
                            native = checked(
                                call["actual_source"],
                                sha(call["actual_source"]),
                                "MICE saved native input",
                            )
                            if (
                                native.size != actual_input.size
                                or native.tobytes() != actual_input.tobytes()
                            ):
                                raise ValueError(
                                    "MICE native input pixels differ from public input"
                                )
                            actual_input = native
                        provenance.append(
                            {
                                "path": str(call_path),
                                "sha256": sha(call_path),
                                "role": "actual model call",
                            }
                        )
                    elif mode == "independent":
                        actual_input = source
                    else:
                        previous = f"{session['session_id']}-{case['turn'] - 1}"
                        previous_mode = "independent" if case["turn"] == 2 else "iterative"
                        prior = read(
                            args.run
                            / "runs"
                            / model
                            / "edit"
                            / track
                            / previous_mode
                            / previous
                            / "result.json"
                        )
                        if prior["status"] == "completed":
                            actual_input = checked(
                                prior["output_image"],
                                prior["output_sha256"],
                                f"{model} preceding output before planning failure",
                            )
                    if result["status"] == "completed":
                        output = checked(
                            result["output_image"], result["output_sha256"], f"{model} output"
                        )
                    elif result["status"] != "failed":
                        raise ValueError("Nonterminal request in final preview")
                    x = margin + (n % 4) * (side + gap)
                    y = header_height + context_height + (n // 4) * block_height
                    panel(canvas, x, y, actual_input, f"{name} | input")
                    panel(
                        canvas,
                        x,
                        y + side + 32,
                        output,
                        "Output" if output else "Generation failed",
                    )
                    score = scores[model, key]
                    values = score.get("metrics", score.get("assigned_penalty"))
                    if values is None:
                        raise ValueError("Missing final score/assigned penalty")
                    foot = [
                        f"L1 {values['L1']:.4f} | L2 {values['L2']:.4f}",
                        f"CLIP-I {values['CLIP-I']:.4f} | DINO {values['DINO']:.4f}",
                        f"CLIP-T {values['CLIP-T']:.4f}"
                        + (" (assigned penalties)" if output is None else ""),
                    ]
                    for j, line in enumerate(foot):
                        draw.text(
                            (x, y + 2 * (side + 28) + 12 + 18 * j), line, font=small, fill="#344158"
                        )
                name = f"{cid}_{track}_{mode}.jpg"
                canvas.save(args.destination / name, quality=94, subsampling=0)
                figures.append({"file": name, "sha256": sha(args.destination / name), "key": key})
    value = {
        "selection": selection,
        "selection_sha256": sha(args.selection),
        "report": str(args.report),
        "report_sha256": sha(args.report),
        "script_sha256": sha(__file__),
        "figures": figures,
        "inputs": provenance,
    }
    (args.destination / "PROVENANCE.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )
    text = [
        "# MagicBrush 固定样例对比",
        "",
        "按预先保存的哈希规则，从共同去重合子集的一／二／三轮会话中各抽一个会话，不按输出或得分挑选。展示其最后一轮的独立输入，以及多轮会话的真实连续输入。全部八方法均展示；失败不换样、不生成替代图。",
        "",
        "每个方法的清图输入在上、输出在下；有 mask 轨道同时给出公开编辑 mask。附加区域条件遵循各方法冻结适配方式。GT 只用于评分与展示，没有送入生成器。图下列五项实测指标；无输出时明确标为约定的失败惩罚。",
        "",
    ]
    for figure in figures:
        text.extend([f"## {figure['key']}", "", f"![{figure['key']}]({figure['file']})", ""])
    (args.destination / "README.md").write_text("\n".join(text))
    print(json.dumps({"figures": len(figures), "destination": str(args.destination)}))


if __name__ == "__main__":
    main()
