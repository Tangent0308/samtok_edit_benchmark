const axes = {edit: "编辑完成度", preservation: "内容保持", quality: "视觉质量"};
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
      const o = document.createElement("option"); o.value = value; o.textContent = value || "请选择"; select.appendChild(o);
    }
    const textarea = document.createElement("textarea"); textarea.id = key+"-evidence"; textarea.rows = 2; textarea.placeholder = "具体视觉依据";
    container.append(title, select, textarea); $("ratings").appendChild(container);
  }
  list();
}
init().catch(error => { $("title").textContent = error.message; });
