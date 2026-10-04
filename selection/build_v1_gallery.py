#!/usr/bin/env python3
"""Build a dependency-free HTML gallery for the instruction-free v1 catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SAMTok Edit Benchmark v1 · Case Gallery</title>
  <style>
    :root { color-scheme: light; --ink:#17202a; --muted:#65727e; --line:#d9e0e6; --panel:#fff; --bg:#f3f6f8; --accent:#1769aa; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
    header { position:sticky; top:0; z-index:5; background:rgba(255,255,255,.97); border-bottom:1px solid var(--line); padding:14px 20px 12px; backdrop-filter: blur(8px); }
    h1 { margin:0 0 5px; font-size:20px; }
    .sub { color:var(--muted); font-size:12px; }
    .controls { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; align-items:center; }
    input, select, button { border:1px solid #bdc8d1; border-radius:6px; background:#fff; color:var(--ink); padding:7px 9px; font:inherit; }
    input[type=search] { width:260px; }
    button { cursor:pointer; background:#f8fafb; }
    button:hover { border-color:var(--accent); color:var(--accent); }
    .counter { margin-left:auto; color:var(--muted); white-space:nowrap; }
    main { max-width:1600px; margin:0 auto; padding:18px 20px 36px; }
    .meta { background:var(--panel); border:1px solid var(--line); border-radius:9px; padding:14px 16px; margin-bottom:14px; }
    .meta-grid { display:grid; grid-template-columns: minmax(0,2fr) repeat(4,minmax(120px,1fr)); gap:12px; }
    .label { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
    .value { margin-top:2px; overflow-wrap:anywhere; }
    .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }
    .views { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
    .card { background:var(--panel); border:1px solid var(--line); border-radius:9px; padding:10px; min-width:0; }
    .card h2 { margin:0 0 8px; font-size:14px; }
    .stage { position:relative; display:flex; justify-content:center; align-items:center; min-height:180px; max-height:62vh; overflow:hidden; background:#e8edf1; border-radius:6px; }
    .stage img { display:block; max-width:100%; max-height:62vh; object-fit:contain; }
    .stage.overlay img:first-child { width:100%; }
    .stage.overlay img:last-child { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; opacity:.48; mix-blend-mode:multiply; }
    .caption { margin-top:7px; color:var(--muted); font-size:12px; }
    .regions { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; margin-top:14px; }
    .region-card { background:var(--panel); border:1px solid var(--line); border-radius:9px; padding:10px; }
    .region-card h3 { margin:0 0 7px; font-size:13px; }
    .region-card img { width:100%; max-height:360px; object-fit:contain; background:#e8edf1; border-radius:6px; display:block; }
    .empty { padding:50px 15px; text-align:center; color:var(--muted); background:var(--panel); border:1px dashed var(--line); border-radius:9px; }
    @media (max-width:900px) { .meta-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .views { grid-template-columns:1fr; } .counter { margin-left:0; } }
  </style>
</head>
<body>
  <header>
    <h1>SAMTok Edit Benchmark v1 · 450-case case gallery</h1>
    <div class="sub">当前版本只展示 source image、evaluation mask、region mask、box 和 point；instruction/target 尚未加入。</div>
    <div class="controls">
      <button id="first">⏮ 首个</button><button id="prev">← 上一个</button><button id="next">下一个 →</button><button id="last">末个 ⏭</button>
      <select id="caseSelect" aria-label="选择 case"></select>
      <input id="search" type="search" placeholder="搜索 ID / 数据集 / source release">
      <select id="releaseFilter"><option value="">全部 release</option></select>
      <select id="datasetFilter"><option value="">全部数据集</option></select>
      <select id="regionFilter"><option value="">全部区域数</option><option value="1">1 region</option><option value="2">2 regions</option></select>
      <span class="counter" id="counter"></span>
    </div>
  </header>
  <main>
    <section class="meta" id="meta"></section>
    <section class="views">
      <article class="card"><h2>Source image</h2><div class="stage"><img id="source" alt="source image"></div><div class="caption" id="sourceCaption"></div></article>
      <article class="card"><h2>Evaluation mask overlay</h2><div class="stage overlay"><img id="sourceOverlay" alt="source image"><img id="evaluation" alt="evaluation mask overlay"></div><div class="caption">红色/深色半透明层为 evaluation mask；单独 mask 见下方 region 卡片。</div></article>
    </section>
    <section class="regions" id="regions"></section>
    <div class="empty" id="empty" hidden>当前筛选条件没有匹配的 case。</div>
  </main>
  <script>
    const CASES = __CASES__;
    const DATASET_ROOT = "__DATASET_ROOT__";
    const state = { filtered: [], position: 0 };
    const $ = id => document.getElementById(id);
    const path = value => DATASET_ROOT + "/" + value;
    const uniqueSorted = key => [...new Set(CASES.map(item => item[key]))].sort((a,b) => a.localeCompare(b));

    function addOptions(select, values) {
      for (const value of values) {
        const option = document.createElement("option"); option.value = value; option.textContent = value; select.appendChild(option);
      }
    }
    addOptions($("releaseFilter"), uniqueSorted("source_release"));
    addOptions($("datasetFilter"), uniqueSorted("source_dataset"));

    function matches(item) {
      const query = $("search").value.trim().toLowerCase();
      const haystack = [item.id, item.original_id, item.source_release, item.source_dataset, item.edit_type].join(" ").toLowerCase();
      return (!query || haystack.includes(query))
        && (!$("releaseFilter").value || item.source_release === $("releaseFilter").value)
        && (!$("datasetFilter").value || item.source_dataset === $("datasetFilter").value)
        && (!$("regionFilter").value || String(item.regions.length) === $("regionFilter").value);
    }
    function refreshFilter(preferredId) {
      const old = preferredId || (state.filtered[state.position] && state.filtered[state.position].id);
      state.filtered = CASES.filter(matches);
      const found = state.filtered.findIndex(item => item.id === old);
      state.position = found >= 0 ? found : 0;
      renderSelect(); render();
    }
    function renderSelect() {
      const select = $("caseSelect"); select.replaceChildren();
      for (let i=0; i<state.filtered.length; i++) {
        const item = state.filtered[i]; const option = document.createElement("option");
        option.value = String(i); option.textContent = `${String(i+1).padStart(3,"0")} · ${item.id}`; select.appendChild(option);
      }
      select.disabled = !state.filtered.length; if (state.filtered.length) select.value = String(state.position);
    }
    function text(parent, label, value, mono=false) {
      const block=document.createElement("div"); const l=document.createElement("div"); l.className="label"; l.textContent=label;
      const v=document.createElement("div"); v.className="value"+(mono?" mono":""); v.textContent=value; block.append(l,v); parent.appendChild(block);
    }
    function render() {
      const item = state.filtered[state.position]; $("counter").textContent = state.filtered.length ? `${state.position+1} / ${state.filtered.length}（全量 ${CASES.length}）` : `0 / 0（全量 ${CASES.length}）`;
      $("empty").hidden = Boolean(item); $("meta").replaceChildren(); $("regions").replaceChildren();
      if (!item) { $("source").removeAttribute("src"); $("sourceOverlay").removeAttribute("src"); $("evaluation").removeAttribute("src"); return; }
      const meta=$("meta"); const grid=document.createElement("div"); grid.className="meta-grid";
      text(grid,"ID",item.id,true); text(grid,"Original ID",item.original_id,true); text(grid,"Release",item.source_release); text(grid,"Dataset",item.source_dataset); text(grid,"Edit type",item.edit_type); meta.appendChild(grid);
      const difficulty=document.createElement("div"); difficulty.className="caption"; difficulty.textContent="Difficulty: "+Object.entries(item.difficulty||{}).filter(([,v])=>v).map(([k])=>k).join(", "); meta.appendChild(difficulty);
      $("source").src=path(item.source_image); $("sourceOverlay").src=path(item.source_image); $("evaluation").src=path(item.evaluation_mask); $("sourceCaption").textContent=item.source_image;
      for (let i=0;i<item.regions.length;i++) {
        const region=item.regions[i], card=document.createElement("article"); card.className="region-card";
        const title=document.createElement("h3"); title.textContent=`Region ${i+1} · box [${region.box.join(", ")}] · point [${region.point.join(", ")}]`; card.appendChild(title);
        const img=document.createElement("img"); img.src=path(region.mask); img.alt=`region ${i+1} mask`; card.appendChild(img);
        const cap=document.createElement("div"); cap.className="caption mono"; cap.textContent=region.mask; card.appendChild(cap); $("regions").appendChild(card);
      }
    }
    function move(delta) { if (!state.filtered.length) return; state.position=Math.max(0,Math.min(state.filtered.length-1,state.position+delta)); renderSelect(); render(); window.scrollTo({top:0,behavior:"smooth"}); }
    $("first").onclick=()=>{state.position=0;renderSelect();render();}; $("prev").onclick=()=>move(-1); $("next").onclick=()=>move(1); $("last").onclick=()=>{state.position=Math.max(0,state.filtered.length-1);renderSelect();render();};
    $("caseSelect").onchange=e=>{state.position=Number(e.target.value);render();};
    for (const id of ["search","releaseFilter","datasetFilter","regionFilter"]) $(id).addEventListener(id==="search"?"input":"change",()=>refreshFilter());
    document.addEventListener("keydown",e=>{if (e.target.matches("input,select")) return; if(e.key==="ArrowLeft")move(-1); if(e.key==="ArrowRight")move(1);});
    refreshFilter(CASES[0] && CASES[0].id);
  </script>
</body>
</html>
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or (root / "case_gallery.html")).resolve()
    manifest = root / "benchmark/benchmark.jsonl"
    cases = [json.loads(line) for line in manifest.open(encoding="utf-8") if line.strip()]
    payload = json.dumps(cases, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</script>", "<\\/script>")
    html = HTML_TEMPLATE.replace("__CASES__", payload).replace("__DATASET_ROOT__", ".")
    output.write_text(html, encoding="utf-8")
    print(json.dumps({"output": str(output), "cases": len(cases), "manifest": str(manifest)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
