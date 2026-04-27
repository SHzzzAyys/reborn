// Reborn polish — single-file frontend.
// State model: each prose block has { id, type, text, polished, issues, status }
// status ∈ "pending" | "polishing" | "reviewing" | "accepted" | "rejected" | "skipped"

const dmp = new diff_match_patch();

const state = {
  filename: null,
  blocks: [],   // raw server blocks merged with UI status fields
  dirty: false,
};

const $ = (id) => document.getElementById(id);
const main = $("main");

async function api(path, opts) {
  const resp = await fetch(path, opts);
  if (!resp.ok) {
    let msg = `${resp.status} ${resp.statusText}`;
    try { const j = await resp.json(); if (j.detail) msg = j.detail; } catch (_) {}
    throw new Error(msg);
  }
  return resp.json();
}

function toast(msg, isError = false) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 2400);
}

function renderDiff(oldText, newText) {
  const diffs = dmp.diff_main(oldText, newText);
  dmp.diff_cleanupSemantic(diffs);
  const frag = document.createDocumentFragment();
  for (const [op, data] of diffs) {
    const safe = document.createTextNode(data);
    if (op === 0) frag.appendChild(safe);
    else if (op === -1) {
      const del = document.createElement("del");
      del.appendChild(safe);
      frag.appendChild(del);
    } else {
      const ins = document.createElement("ins");
      ins.appendChild(safe);
      frag.appendChild(ins);
    }
  }
  return frag;
}

function updateStats() {
  const prose = state.blocks.filter((b) => b.type === "prose");
  const accepted = prose.filter((b) => b.status === "accepted").length;
  const polished = prose.filter((b) => b.status === "reviewing").length;
  $("stats").textContent =
    `${prose.length} 段正文 · 待审 ${polished} · 已接受 ${accepted}`;
  $("save").disabled = !state.dirty;
}

function setStatus(block, status) {
  block.status = status;
  if (status === "accepted") state.dirty = true;
  renderCard(block);
  updateStats();
}

function renderCard(block) {
  const card = document.querySelector(`[data-id="${block.id}"]`);
  if (!card) return;
  card.className = "card " + block.type + " " + (block.status || "");

  if (block.type === "skip") {
    const pre = document.createElement("pre");
    pre.textContent = block.text;
    card.replaceChildren(pre);
    return;
  }

  // Prose block.
  const raw = document.createElement("div");
  raw.className = "raw";
  // Show whatever is currently the canonical text for this block.
  raw.textContent = block.status === "accepted" ? block.polished : block.text;
  card.replaceChildren(raw);

  if (block.status === "reviewing" && block.polished != null) {
    const diffBox = document.createElement("div");
    diffBox.className = "diff";
    diffBox.appendChild(renderDiff(block.text, block.polished));
    card.appendChild(diffBox);

    if (block.issues && block.issues.length) {
      const issues = document.createElement("div");
      issues.className = "issues";
      issues.innerHTML = "<strong>修改说明：</strong>";
      const ul = document.createElement("ul");
      for (const it of block.issues) {
        const li = document.createElement("li");
        li.textContent = it;
        ul.appendChild(li);
      }
      issues.appendChild(ul);
      card.appendChild(issues);
    }
  }

  const actions = document.createElement("div");
  actions.className = "actions";
  const status = document.createElement("span");
  status.className = "status";

  if (block.status === "accepted") status.textContent = "✓ 已接受";
  else if (block.status === "rejected") status.textContent = "✗ 已拒绝";
  else if (block.status === "skipped") status.textContent = "— 已跳过";
  else if (block.status === "polishing") status.textContent = "润色中…";
  actions.appendChild(status);

  const spacer = document.createElement("span");
  spacer.className = "spacer";
  actions.appendChild(spacer);

  if (block.status === "reviewing") {
    actions.appendChild(makeBtn("接受", "primary", () => acceptBlock(block)));
    actions.appendChild(makeBtn("拒绝", "", () => setStatus(block, "rejected")));
    actions.appendChild(makeBtn("重新润色", "", () => polishBlock(block, true)));
  } else if (block.status === "accepted") {
    actions.appendChild(makeBtn("撤销", "", () => {
      block.polished = null; block.issues = []; state.dirty = recomputeDirty();
      setStatus(block, "pending");
    }));
  } else {
    const polishBtn = makeBtn(
      block.polished ? "重新润色" : "润色这段",
      "",
      () => polishBlock(block),
    );
    polishBtn.disabled = block.status === "polishing";
    actions.appendChild(polishBtn);
    if (block.status !== "skipped") {
      actions.appendChild(makeBtn("跳过", "", () => setStatus(block, "skipped")));
    }
  }

  card.appendChild(actions);
}

function makeBtn(label, cls, onClick) {
  const b = document.createElement("button");
  b.textContent = label;
  if (cls) b.className = cls;
  b.addEventListener("click", onClick);
  return b;
}

function recomputeDirty() {
  return state.blocks.some((b) => b.type === "prose" && b.status === "accepted");
}

function acceptBlock(block) {
  // Replace block.text with polished — that becomes the canonical content
  // that gets written back to disk. Preserve trailing newline structure.
  const orig = block.text;
  const trailing = orig.match(/\n*$/)[0];
  const polishedTrimmed = block.polished.replace(/\n*$/, "");
  block.text = polishedTrimmed + trailing;
  setStatus(block, "accepted");
}

async function polishBlock(block, force = false) {
  if (block.status === "polishing") return;
  if (!force && block.status === "accepted") return;
  setStatus(block, "polishing");
  try {
    const r = await api("/api/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: block.text }),
    });
    block.polished = r.polished;
    block.issues = r.issues || [];
    if (block.polished.trim() === block.text.trim()) {
      // No real change — auto-mark as skipped to reduce noise.
      block.status = "skipped";
      toast("这段无需修改");
    } else {
      block.status = "reviewing";
    }
    renderCard(block);
    updateStats();
  } catch (e) {
    block.status = "pending";
    renderCard(block);
    toast("润色失败：" + e.message, true);
  }
}

async function loadFile(name) {
  if (state.dirty && !confirm("有未保存的修改，切换文件会丢失。确定继续？")) {
    $("file-select").value = state.filename || "";
    return;
  }
  state.filename = name;
  state.dirty = false;
  main.replaceChildren();
  if (!name) { updateStats(); return; }

  try {
    const r = await api("/api/file?name=" + encodeURIComponent(name));
    state.blocks = r.blocks.map((b) => ({
      ...b,
      polished: null,
      issues: [],
      status: "pending",
    }));
    for (const b of state.blocks) {
      const card = document.createElement("div");
      card.className = "card " + b.type;
      card.dataset.id = b.id;
      main.appendChild(card);
      renderCard(b);
    }
    updateStats();
  } catch (e) {
    toast("加载失败：" + e.message, true);
  }
}

async function polishAll() {
  const targets = state.blocks.filter(
    (b) => b.type === "prose" && b.status === "pending",
  );
  if (!targets.length) { toast("没有待润色的段落"); return; }
  $("polish-all").disabled = true;
  for (const b of targets) {
    await polishBlock(b);
  }
  $("polish-all").disabled = false;
}

async function saveFile() {
  if (!state.filename || !state.dirty) return;
  const payload = {
    name: state.filename,
    blocks: state.blocks.map(({ id, type, text }) => ({ id, type, text })),
  };
  try {
    const r = await api("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.dirty = false;
    updateStats();
    toast(`已保存 (${r.bytes} 字节)，备份：${r.backup}`);
  } catch (e) {
    toast("保存失败：" + e.message, true);
  }
}

async function init() {
  try {
    const r = await api("/api/files");
    const sel = $("file-select");
    for (const name of r.files) {
      const opt = document.createElement("option");
      opt.value = name; opt.textContent = name;
      sel.appendChild(opt);
    }
  } catch (e) {
    toast("读取文件列表失败：" + e.message, true);
  }
  $("file-select").addEventListener("change", (e) => loadFile(e.target.value));
  $("polish-all").addEventListener("click", polishAll);
  $("save").addEventListener("click", saveFile);
  window.addEventListener("beforeunload", (e) => {
    if (state.dirty) { e.preventDefault(); e.returnValue = ""; }
  });
}

init();
