"""Plot all prespecified paired effects from the final report, without recomputing scores."""

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("MPLBACKEND", "Agg")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from samtok_benchmark.io import sha256_file
from samtok_benchmark.external_full.data import immutable


def run(report, output):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    payload = json.loads(Path(report).read_text())
    bench = payload["benchmark"]
    rows = payload["analysis"]["rows"]
    metrics = list(dict.fromkeys(r["metric"] for r in rows if r["main_endpoint"]))
    if bench == "compbench":
        groups = list(dict.fromkeys(r["group"] for r in rows if r["main_endpoint"]))
        columns, figsize = 5, (18, 4.1)
    elif bench == "interedit":
        groups = ["all"] + list(
            dict.fromkeys(r["group"] for r in rows if r["group"].startswith("task/"))
        )
        columns, figsize = 4, (15, 4.6)
    else:
        groups = ["all", "task/low", "task/high"]
        columns, figsize = 4, (15, 6.5)
    names = {
        "all": "Overall",
        "Local Editing": "Local editing",
        "Multi-object Editing": "Multi-object",
        "Implicit Reasoning": "Implicit",
        "Multi-turn (Turn 1)": "Turn 1",
        "Multi-turn (Turn 2)": "Turn 2",
    }
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )
    fig, axes = plt.subplots(
        (len(metrics) + columns - 1) // columns, columns, figsize=figsize, squeeze=False
    )
    lookup = {(r["group"], r["metric"]): r for r in rows}
    for ax, key in zip(axes.flat, metrics):
        for i, group in enumerate(groups):
            row = lookup[group, key]
            point = row["benefit_delta"]
            interval = row["benefit_CI95"]
            if point is None or interval is None:
                ax.text(0, i, "N/A", va="center")
                continue
            significant = row.get("p_holm_53", 1) < 0.05 and interval[0] > 0
            color = "#0072B2" if point >= 0 else "#D55E00"
            ax.plot(interval, [i, i], color=color, lw=2)
            ax.plot(
                point,
                i,
                marker="*" if significant else "o",
                color=color,
                ms=11 if significant else 5,
            )
        ax.axvline(0, color="#777", lw=0.9, ls="--")
        ax.set_yticks(range(len(groups)), [names.get(g, g.removeprefix("task/")) for g in groups])
        ax.invert_yaxis()
        ax.set_title(key, weight="bold")
        ax.set_xlabel("Benefit over Base (native units)")
        ax.grid(axis="x", alpha=0.15)
        ax.margins(x=0.18, y=0.15)
    for ax in list(axes.flat)[len(metrics) :]:
        ax.set_visible(False)
    fig.suptitle(
        f"{bench}: SITEdit versus Qwen-Image-2.1 | fixed new cohort", fontsize=14, weight="bold"
    )
    handles = [
        Line2D([], [], color="#0072B2", marker="o", label="Estimate favors SITEdit"),
        Line2D([], [], color="#D55E00", marker="o", label="Estimate favors Base"),
        Line2D(
            [],
            [],
            color="#222",
            marker="*",
            linestyle="None",
            markersize=11,
            label="Main endpoint: Holm p < 0.05; CI > 0",
        ),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False)
    fig.text(
        0.5,
        0.065 if bench != "omni_iie" else 0.055,
        "Bars: pointwise 95% source-paired bootstrap CI. Positive always favors SITEdit. No composite score.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.11 if bench != "omni_iie" else 0.085, 1, 0.94))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "pdf"):
        fig.savefig(
            out / f"PAIRED_EFFECTS.{extension}",
            dpi=180,
            bbox_inches="tight",
            metadata={"CreationDate": None, "ModDate": None}
            if extension == "pdf"
            else {"Software": "IF-Bench paired validation"},
        )
    plt.close(fig)
    immutable(
        out / "PAIRED_EFFECTS_PROVENANCE.json",
        {
            "source_report": str(Path(report).resolve()),
            "sha256": sha256_file(report),
            "script_sha256": sha256_file(__file__),
            "policy": "All main endpoints; Inter task breakdown additionally shown as diagnosis. No outcome-based endpoint selection.",
            "outputs": {ext: sha256_file(out / f"PAIRED_EFFECTS.{ext}") for ext in ("png", "pdf")},
        },
    )
    print(out / "PAIRED_EFFECTS.png")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", required=True)
    p.add_argument("--output", required=True)
    run(**vars(p.parse_args()))
