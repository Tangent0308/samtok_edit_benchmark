const state = {
  cases: [],
  results: { version: 1, cases: {} },
  filtered: [],
  current: -1,
  saveTimer: null,
};

const $ = (id) => document.getElementById(id);

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

async function loadResults() {
  try {
    const data = await loadJson("/api/results");
    if (data && typeof data.cases === "object") return data;
  } catch (_) {
    // Opening index.html directly still works; localStorage is the fallback.
  }
  try {
    const data = JSON.parse(localStorage.getItem("samtok_v1_review_results") || "{}");
    if (data && typeof data.cases === "object") return data;
  } catch (_) {}
  return { version: 1, cases: {} };
}

function currentCase() {
  return state.filtered[state.current] || null;
}

function statusFor(id) {
  return state.results.cases[id]?.status || "unreviewed";
}

function applyFilter() {
  const selectedId = currentCase()?.id;
  const query = $("search").value.trim().toLowerCase();
  const filter = $("filter").value;
  state.filtered = state.cases.filter((item) => {
    const text = [item.id, item.original_id, item.source_release, item.source_dataset, item.edit_type].join(" ").toLowerCase();
    const matchesText = !query || text.includes(query);
    const status = statusFor(item.id);
    return matchesText && (filter === "all" || status === filter);
  });
  state.current = selectedId ? state.filtered.findIndex(item => item.id === selectedId) : -1;
  renderList();
  renderCase();
}

function renderList() {
  const list = $("case-list");
  list.replaceChildren();
  state.filtered.forEach((item, index) => {
    const link = document.createElement("div");
    const status = statusFor(item.id);
    link.className = `case-link ${status}${index === state.current ? " active" : ""}`;
    link.setAttribute("role", "button");
    link.tabIndex = 0;
    link.innerHTML = `<span><span class="case-id">#${String(item.index).padStart(4, "0")}</span> <span class="case-type">${item.edit_type}</span></span><span class="dot" title="${status}"></span>`;
    link.addEventListener("click", () => selectIndex(index));
    link.addEventListener("keydown", (event) => { if (event.key === "Enter") selectIndex(index); });
    list.appendChild(link);
  });
  const counts = { pass: 0, discard: 0 };
  Object.values(state.results.cases).forEach((record) => { if (counts[record.status] !== undefined) counts[record.status] += 1; });
  $("total-count").textContent = state.cases.length;
  $("pass-count").textContent = counts.pass;
  $("discard-count").textContent = counts.discard;
  $("todo-count").textContent = Math.max(0, state.cases.length - counts.pass - counts.discard);
}

function selectIndex(index) {
  state.current = index;
  renderList();
  renderCase();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderMetadata(item) {
  const difficulty = Object.entries(item.difficulty || {}).filter(([, value]) => value).map(([key]) => key);
  const values = [
    ["ID", item.id],
    ["来源", item.source_release],
    ["数据集", item.source_dataset],
    ["编辑类型", item.edit_type],
    ["区域数", String((item.regions || []).length)],
    ["难度标签", difficulty.length ? difficulty.join(", ") : "无"],
  ];
  $("metadata").replaceChildren(...values.map(([key, value]) => {
    const node = document.createElement("div");
    node.className = "meta-item";
    node.innerHTML = `<strong>${key}</strong> ${value}`;
    return node;
  }));
}

function renderCase() {
  const item = currentCase();
  $("empty").hidden = Boolean(item);
  $("case-view").hidden = !item;
  if (!item) {
    $("case-title").textContent = state.filtered.length ? "请选择一个 case" : "没有匹配的 case";
    $("case-subtitle").textContent = "选择后按需加载原图和原始 region mask。";
    $("source-image").removeAttribute("src");
    $("overlay-image").removeAttribute("src");
    $("region-images").replaceChildren();
    return;
  }
  $("case-title").textContent = `#${String(item.index).padStart(4, "0")} · ${item.id}`;
  $("case-subtitle").textContent = `${item.source_release} · ${item.source_dataset} · ${item.edit_type}`;
  renderMetadata(item);
  $("source-image").src = item.source_image;
  $("overlay-image").src = item.mask_overlay || "";
  const review = state.results.cases[item.id] || {};
  const changed = review.updated_at && item.instruction_revision && review.instruction_revision !== item.instruction_revision;
  $("original-instruction").textContent = `本版指令：${item.instruction || "（无）"}${changed ? " · 指令已修订，请重新核对原有判断。" : ""}`;
  $("instruction-edit").value = review.instruction_override || item.instruction || "";
  const regionImages = $("region-images");
  regionImages.replaceChildren();
  (item.regions || []).forEach((region, index) => {
    const label = document.createElement("div");
    label.className = "region-label";
    label.textContent = `region ${index + 1} · box ${JSON.stringify(region.box || [])} · point ${JSON.stringify(region.point || [])}`;
    const image = document.createElement("img");
    image.src = region.mask;
    image.alt = `region ${index + 1} mask`;
    regionImages.append(label, image);
  });
  const status = statusFor(item.id);
  $("current-status").className = `status-badge ${status}`;
  $("current-status").textContent = status === "pass" ? "已通过" : status === "discard" ? "已丢弃" : "未处理";
  $("note").value = state.results.cases[item.id]?.note || "";
  renderRaw(item);
}

function renderRaw(item) {
  const visible = { ...item };
  delete visible.evaluation_mask;
  $("raw-json").textContent = JSON.stringify({ case: visible, review: state.results.cases[item.id] || { status: "unreviewed" } }, null, 2);
}

async function persist() {
  const payload = JSON.stringify(state.results);
  localStorage.setItem("samtok_v1_review_results", payload);
  try {
    const response = await fetch("/api/results", { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    showSaveMessage("已保存到 review_results.json");
  } catch (_) {
    showSaveMessage("已保存到浏览器本地；使用 run_review.py 时会同步写入 review_results.json");
  }
}

function showSaveMessage(message) {
  $("save-message").textContent = message;
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => { $("save-message").textContent = ""; }, 2800);
}

function setStatus(status) {
  const item = currentCase();
  if (!item) return;
  const note = $("note").value.trim();
  const instruction = $("instruction-edit").value.trim();
  if (status === "pass" && !instruction) { showSaveMessage("通过前请填写有效编辑指令。"); return; }
  if (status === "unreviewed" && !note && !instruction && instruction === (item.instruction || "")) delete state.results.cases[item.id];
  else state.results.cases[item.id] = { status, note, instruction_override: instruction, instruction_revision: item.instruction_revision || "v0_original", updated_at: new Date().toISOString() };
  renderList();
  renderCase();
  persist();
}

function saveInstruction() {
  const item = currentCase();
  if (!item) return;
  const instruction = $("instruction-edit").value.trim();
  const previous = state.results.cases[item.id] || {};
  if (instruction === (previous.instruction_override || item.instruction || "")) return;
  state.results.cases[item.id] = {
    status: "unreviewed",
    instruction_revision: item.instruction_revision,
    note: previous.note || "",
    instruction_override: instruction,
    updated_at: new Date().toISOString(),
  };
  renderList();
  renderRaw(item);
  persist();
}

function exportResults() {
  const blob = new Blob([JSON.stringify(state.results, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "review_results.json";
  anchor.click();
  URL.revokeObjectURL(url);
}

function move(delta) {
  if (!state.filtered.length) return;
  selectIndex(Math.min(state.filtered.length - 1, Math.max(0, state.current + delta)));
}

async function init() {
  try {
    state.cases = await loadJson("cases.json");
    state.results = await loadResults();
    // Old decisions often saved the then-default instruction as an override.
    // Preserve genuine user edits, but never resurrect the erroneous old default.
    const revisionResponse = await fetch("benchmark/instruction_revision_audit.jsonl", { cache: "no-store" });
    const revisions = revisionResponse.ok ? (await revisionResponse.text())
      .trim().split("\n").filter(Boolean).map(line => JSON.parse(line)) : [];
    for (const revision of revisions) {
      const record = state.results.cases[revision.id];
      if (record?.instruction_override === revision.previous_instruction) delete record.instruction_override;
    }
    $("search").addEventListener("input", applyFilter);
    $("filter").addEventListener("change", applyFilter);
    $("pass").addEventListener("click", () => setStatus("pass"));
    $("discard").addEventListener("click", () => setStatus("discard"));
    $("unset").addEventListener("click", () => setStatus("unreviewed"));
    $("prev").addEventListener("click", () => move(-1));
    $("next").addEventListener("click", () => move(1));
    $("export").addEventListener("click", exportResults);
    $("instruction-edit").addEventListener("change", saveInstruction);
    $("instruction-edit").addEventListener("blur", saveInstruction);
    $("note").addEventListener("change", () => {
      const item = currentCase();
      if (!item || !state.results.cases[item.id]) return;
      state.results.cases[item.id].note = $("note").value.trim();
      state.results.cases[item.id].updated_at = new Date().toISOString();
      persist();
    });
    document.addEventListener("keydown", (event) => {
      if (event.target.matches("input, textarea, select")) return;
      if (event.key === "p" || event.key === "P") setStatus("pass");
      if (event.key === "d" || event.key === "D") setStatus("discard");
      if (event.key === "u" || event.key === "U") setStatus("unreviewed");
      if (event.key === "ArrowLeft") move(-1);
      if (event.key === "ArrowRight") move(1);
    });
    applyFilter();
  } catch (error) {
    $("case-title").textContent = "加载失败";
    $("case-subtitle").textContent = String(error);
  }
}

init();
