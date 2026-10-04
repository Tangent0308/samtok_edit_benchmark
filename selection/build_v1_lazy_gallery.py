#!/usr/bin/env python3
"""Build a lazy-loading case gallery and per-case preview files."""

from __future__ import annotations

import argparse
import base64
import html as html_lib
import json
import shutil
from pathlib import Path

from build_v1_gallery import _preview_for_case


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SAMTok Edit Benchmark v1 · Lazy Case Gallery</title>
  <style>
    :root { --ink:#17202a; --muted:#687681; --line:#d9e0e6; --panel:#fff; --bg:#f3f6f8; --accent:#1769aa; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:var(--bg); font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
    header { position:sticky; top:0; z-index:4; background:rgba(255,255,255,.98); border-bottom:1px solid var(--line); padding:12px 16px; }
    h1 { margin:0 0 4px; font-size:19px; } .sub { color:var(--muted); font-size:12px; }
    .toolbar { display:flex; flex-wrap:wrap; gap:7px; align-items:center; margin-top:10px; }
    input,select,button { border:1px solid #bdc8d1; border-radius:6px; background:#fff; padding:7px 9px; color:var(--ink); font:inherit; }
    input[type=search] { width:260px; } button { cursor:pointer; } button:hover { color:var(--accent); border-color:var(--accent); }
    .count { color:var(--muted); margin-left:auto; }
    .layout { display:grid; grid-template-columns:330px minmax(0,1fr); min-height:calc(100vh - 126px); }
    aside { position:sticky; top:126px; height:calc(100vh - 126px); overflow:auto; border-right:1px solid var(--line); background:#f8fafb; padding:9px; }
    .case-list { display:grid; gap:5px; }
    .case-item { width:100%; text-align:left; border:1px solid transparent; border-radius:6px; background:transparent; padding:8px 9px; cursor:pointer; }
    .case-item:hover { background:#eaf3fa; } .case-item.active { border-color:#77acd0; background:#dceefa; }
    .case-number { color:var(--muted); font-size:11px; margin-right:5px; } .case-id { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:11px; overflow-wrap:anywhere; }
    .case-sub { color:var(--muted); font-size:11px; margin-top:3px; }
    main { min-width:0; padding:16px 20px 34px; }
    .empty { max-width:800px; margin:16vh auto; padding:42px 20px; text-align:center; border:1px dashed var(--line); border-radius:9px; color:var(--muted); background:var(--panel); }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:9px; padding:13px; margin-bottom:13px; }
    .meta-grid { display:grid; grid-template-columns:minmax(0,2fr) repeat(4,minmax(100px,1fr)); gap:10px; }
    .label { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; } .value { margin-top:2px; overflow-wrap:anywhere; }
    .mono { font:12px ui-monospace,SFMono-Regular,Menlo,monospace; }
    .preview-wrap { display:flex; justify-content:center; min-height:260px; background:#e8edf1; border-radius:6px; overflow:auto; }
    #preview { display:block; max-width:100%; height:auto; object-fit:contain; }
    .caption { color:var(--muted); font-size:12px; margin-top:7px; overflow-wrap:anywhere; }
    .regions { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:9px; }
    .region { border-top:1px solid var(--line); padding-top:9px; }
    @media(max-width:900px) { .layout { grid-template-columns:1fr; } aside { position:static; height:auto; max-height:36vh; border-right:0; border-bottom:1px solid var(--line); } .meta-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .count { margin-left:0; } }
  </style>
</head>
<body>
  <header>
    <h1>SAMTok Edit Benchmark v1 · lazy case gallery</h1>
    <div class="sub">初始只加载 case 列表和元数据；选中后才加载该 case 的一张压缩预览图。预览包含 source、evaluation mask 和 region mask。</div>
    <div class="toolbar">
      <input id="search" type="search" placeholder="搜索 ID / 数据集 / release">
      <select id="release"><option value="">全部 release</option></select>
      <select id="dataset"><option value="">全部数据集</option></select>
      <select id="regions"><option value="">全部区域数</option><option value="1">1 region</option><option value="2">2 regions</option></select>
      <button id="previous">← 上一个</button><button id="next">下一个 →</button>
      <span class="count" id="count"></span>
    </div>
  </header>
  <div class="layout">
    <aside><div class="case-list" id="caseList">__STATIC_LIST__</div></aside>
    <main>
      <div class="empty" id="empty">请从左侧选择一个 case。当前尚未加载任何图片。</div>
      <section id="detail" hidden>
        <div class="panel" id="meta"></div>
        <div class="panel"><div class="preview-wrap"><img id="preview" alt="selected case preview"></div><div class="caption" id="previewCaption"></div></div>
        <div class="panel"><div class="regions" id="regionInfo"></div></div>
      </section>
    </main>
  </div>
  <script id="case-data" type="application/json">__CASES__</script>
  <script src="case_gallery.js"></script>
</body>
</html>
'''


LAZY_JS = r'''const CASES = JSON.parse(document.getElementById("case-data").textContent);
const state = { filtered: CASES.slice(), selectedId: null };
const $ = id => document.getElementById(id);
const values = key => [...new Set(CASES.map(x => x[key]))].sort((a,b)=>a.localeCompare(b));
for (const value of values("source_release")) { const o=document.createElement("option"); o.value=value; o.textContent=value; $("release").appendChild(o); }
for (const value of values("source_dataset")) { const o=document.createElement("option"); o.value=value; o.textContent=value; $("dataset").appendChild(o); }
function match(x) {
  const q=$("search").value.trim().toLowerCase(); const text=[x.id,x.original_id,x.source_release,x.source_dataset,x.edit_type].join(" ").toLowerCase();
  return (!q || text.includes(q)) && (!$('release').value || x.source_release===$('release').value) && (!$('dataset').value || x.source_dataset===$('dataset').value) && (!$('regions').value || String(x.regions.length)===$('regions').value);
}
function refresh() { const keep=state.selectedId; state.filtered=CASES.filter(match); renderList(); if (keep && state.filtered.some(x=>x.id===keep)) select(keep); else { state.selectedId=null; showEmpty(); } }
function renderList() {
  const list=$("caseList"); list.replaceChildren(); $("count").textContent=`${state.filtered.length} / ${CASES.length} cases`;
  for (let i=0;i<state.filtered.length;i++) { const item=state.filtered[i], b=document.createElement("button"); b.className="case-item"+(item.id===state.selectedId?" active":""); b.dataset.id=item.id;
    b.innerHTML=`<span class="case-number">${String(i+1).padStart(3,"0")}</span><span class="case-id"></span><div class="case-sub"></div>`;
    b.querySelector('.case-id').textContent=item.id; b.querySelector('.case-sub').textContent=`${item.source_dataset} · ${item.regions.length} region · ${item.edit_type}`; list.appendChild(b); }
}
function showEmpty() { $("empty").hidden=false; $("detail").hidden=true; $("preview").removeAttribute("src"); }
function select(id) {
  const item=CASES.find(x=>x.id===id); if (!item) return; state.selectedId=id; $("empty").hidden=true; $("detail").hidden=false;
  const meta=$("meta"); meta.replaceChildren(); const grid=document.createElement("div"); grid.className="meta-grid";
  const add=(label,value,mono=false)=>{const d=document.createElement('div'),l=document.createElement('div'),v=document.createElement('div');l.className='label';l.textContent=label;v.className='value'+(mono?' mono':'');v.textContent=value;d.append(l,v);grid.appendChild(d);};
  add('ID',item.id,true); add('Original ID',item.original_id,true); add('Release',item.source_release); add('Dataset',item.source_dataset); add('Edit type',item.edit_type); meta.appendChild(grid);
  const difficulty=document.createElement('div'); difficulty.className='caption'; difficulty.textContent='Difficulty: '+Object.entries(item.difficulty||{}).filter(([,v])=>v).map(([k])=>k).join(', '); meta.appendChild(difficulty);
  const image=new Image(); image.onload=()=>{if(state.selectedId===id) $("preview").replaceWith(image);}; image.onerror=()=>{if(state.selectedId===id) $("previewCaption").textContent='预览图加载失败，请使用 serve_v1_gallery.py 启动本地服务。';}; image.alt='selected case preview'; image.id='preview'; image.src=item.preview;
  $("previewCaption").textContent=`已请求当前 case 预览（${item.preview_size_kb} KB）；原始源图：${item.source_image}`;
  const regions=$("regionInfo"); regions.replaceChildren(); item.regions.forEach((r,i)=>{const d=document.createElement('div');d.className='region';d.innerHTML=`<b>Region ${i+1}</b><div class="caption">box [${r.box.join(', ')}] · point [${r.point.join(', ')}]<br><span class="mono"></span></div>`;d.querySelector('span').textContent=r.mask;regions.appendChild(d);});
  renderList();
}
$("caseList").onclick=e=>{const button=e.target.closest('.case-item');if(button)select(button.dataset.id);};
$("previous").onclick=()=>{const i=state.filtered.findIndex(x=>x.id===state.selectedId);if(i>0)select(state.filtered[i-1].id);};
$("next").onclick=()=>{const i=state.filtered.findIndex(x=>x.id===state.selectedId);if(i>=0&&i<state.filtered.length-1)select(state.filtered[i+1].id);};
for(const id of ['search','release','dataset','regions']) $(id).addEventListener(id==='search'?'input':'change',refresh);
document.addEventListener('keydown',e=>{if(e.target.matches('input,select'))return;if(e.key==='ArrowLeft')$("previous").click();if(e.key==='ArrowRight')$("next").click();});
renderList();
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--clean", action="store_true", help="remove old preview files first")
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or (root / "case_gallery.html")).resolve()
    manifest = root / "benchmark/benchmark.jsonl"
    preview_dir = root / "gallery_previews"
    if args.clean and preview_dir.exists(): shutil.rmtree(preview_dir)
    preview_dir.mkdir(parents=True, exist_ok=True)
    cases = [json.loads(line) for line in manifest.open(encoding="utf-8") if line.strip()]
    metadata = []
    for index, case in enumerate(cases):
        preview_name = f"{index:04d}.jpg"
        preview_path = preview_dir / preview_name
        if not preview_path.is_file():
            data_uri = _preview_for_case(root, case)
            preview_path.write_bytes(base64.b64decode(data_uri.split(",", 1)[1]))
        item = dict(case)
        item["preview"] = f"gallery_previews/{preview_name}"
        item["preview_size_kb"] = round(preview_path.stat().st_size / 1024, 1)
        metadata.append(item)
    payload = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).replace("</script>", "<\\/script>")
    static_buttons = []
    for index, item in enumerate(metadata):
        case_id = html_lib.escape(item["id"], quote=True)
        dataset = html_lib.escape(f"{item['source_dataset']} · {len(item['regions'])} region · {item['edit_type']}")
        static_buttons.append(
            f'<button class="case-item" data-id="{case_id}"><span class="case-number">{index + 1:03d}</span>'
            f'<span class="case-id">{case_id}</span><div class="case-sub">{dataset}</div></button>'
        )
    output.write_text(
        HTML.replace("__CASES__", payload).replace("__STATIC_LIST__", "".join(static_buttons)),
        encoding="utf-8",
    )
    (output.parent / "case_gallery.js").write_text(LAZY_JS, encoding="utf-8")
    (root / "gallery_cases.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "cases": len(metadata), "preview_dir": str(preview_dir), "total_preview_bytes": sum(p.stat().st_size for p in preview_dir.glob("*.jpg"))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
