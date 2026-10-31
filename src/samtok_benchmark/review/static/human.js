const axes = {edit: "目标编辑完成度（没有少编辑）", preservation: "内容保持（没有多编辑）", quality: "视觉质量（没有新缺陷）"};
const anchors = {
  edit: ["正确目标无相关进展／只改错实例或部件", "正确目标处仅有无效或表面尝试", "实质部分完成／漏目标或部件／显式属性或数量错误", "所有目标基本完成，仅有可指出的小局部残留", "所有正确目标的显式要求完整满足"],
  preservation: ["大部分应保护场景被替换或破坏", "重大身份或结构损伤／多个对象或广泛场景被实质误改", "至少一处明确局部误改，再小也算", "只有轻微低层纹理或边缘差异，无明确对象或属性误改", "未授权内容保持，只有必要融合与可忽略采样差异"],
  quality: ["输出视觉不可用／图像结构大面积损坏", "目标局部结构严重损坏／多个严重新缺陷", "明确接缝、光晕、畸形、接触或光影错误", "仅小局部边缘或纹理瑕疵，结构与接触仍连贯", "检查后无可指出的新渲染缺陷"]
};
const evidenceHints = {
  edit: "逐个 R 写出实例/部件、原来是什么、现在是什么、满足或缺失的要求。3 分须指出残留；null 须说明看不清的具体内容。",
  preservation: "依次对照目标/所属物体的未改部件、邻近/易混淆对象及遮挡物、其余场景。指出最严重的额外变化，或实际比较过的具体内容。",
  quality: "写出新缺陷的位置与程度，或检查到的连贯边界、结构/接触和纹理/光照。原有模糊、画风与干净的错改不扣此项。"
};
const state = {samples: [], current: null, scores: {}, storage: ""};
const $ = id => document.getElementById(id);
function list() {
  $("case-list").replaceChildren(...state.samples.map((s, i) => {
    const button = document.createElement("button");
    button.className = "case-link";
    button.textContent = `${String(i+1).padStart(4,"0")} ${state.scores[s.sample_id] ? "✓" : ""}`;
    button.onclick = () => select(s);
    return button;
  }));
}
function select(sample) {
  state.current = sample;
  $("case-view").hidden = false;
  $("title").textContent = `样例 ${sample.index+1}`;
  $("instruction").textContent = sample.instruction;
  for (const key of ["before_clean", "after_clean", "before_contours", "after_contours"]) {
    const id = key.replace("_clean", "").replace("_", "-");
    $(id).src = sample[key]; $(id+"-link").href = sample[key];
  }
  $("message").textContent = "";
  for (const key of Object.keys(axes)) {
    const r = state.scores[sample.sample_id];
    $(key).value = r ? (r[key] === null ? "unknown" : String(r[key])) : "";
    $(key+"-evidence").value = r?.[key+"_evidence"] || "";
  }
}
$("save").onclick = () => {
  if (!state.current) return;
  const result = {sample_id: state.current.sample_id, input_digest: state.current.input_digest,
    reviewer: state.current.reviewer, recorded_at: new Date().toISOString()};
  for (const key of Object.keys(axes)) {
    const value = $(key).value, evidence = $(key+"-evidence").value.trim();
    if (!value || !evidence) { $("message").textContent = "每项请选择分数并填写具体视觉依据。"; return; }
    result[key] = value === "unknown" ? null : Number(value);
    result[key+"_evidence"] = evidence;
  }
  state.scores[result.sample_id] = result;
  localStorage.setItem(state.storage, JSON.stringify(state.scores));
  list(); $("message").textContent = "已保存到当前浏览器；请导出结果文件。";
};
$("export").onclick = () => {
  const blob = new Blob([Object.values(state.scores).map(s => JSON.stringify(s)+"\n").join("")], {type:"application/x-ndjson"});
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = "human_scores.jsonl"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
};
async function init() {
  const response = await fetch("samples.json");
  if (!response.ok) throw new Error(`samples.json: ${response.status}`);
  state.samples = await response.json();
  state.storage = `samtok-human-${state.samples[0]?.reviewer}-${state.samples[0]?.input_digest}`;
  state.scores = JSON.parse(localStorage.getItem(state.storage) || "{}");
  $("reviewer").textContent = `审核者：${state.samples[0]?.reviewer || ""} · ${state.samples.length} 个结果`;
  for (const [key, label] of Object.entries(axes)) {
    const container = document.createElement("div");
    const title = document.createElement("label"); title.textContent = label;
    const select = document.createElement("select"); select.id = key;
    for (const value of ["", "0", "1", "2", "3", "4", "unknown"]) {
      const o = document.createElement("option"); o.value = value;
      o.textContent = value === "" ? "请选择" : value === "unknown" ? "unknown · 有具体证据障碍，无法确定等级" : `${value} · ${anchors[key][Number(value)]}`;
      select.appendChild(o);
    }
    const hint = document.createElement("p"); hint.className = "muted"; hint.textContent = evidenceHints[key];
    const textarea = document.createElement("textarea"); textarea.id = key+"-evidence"; textarea.rows = 3; textarea.placeholder = evidenceHints[key];
    container.append(title, select, hint, textarea); $("ratings").appendChild(container);
  }
  list();
}
init().catch(error => { $("title").textContent = error.message; });
