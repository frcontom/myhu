const $ = (id) => document.getElementById(id);

let state = {
  workItem: null,
  testCases: [],
  huMap: {},
};

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.detail || `Error HTTP ${resp.status}`);
  }
  return data;
}

function setLoading(on, text) {
  $("loader").classList.toggle("hidden", !on);
  if (on && text) $("loader-text").textContent = text;
}

function setProgress(percent, statsText) {
  $("progress-bar").style.width = Math.min(100, Math.max(0, percent)) + "%";
  if (statsText) $("loader-stats").textContent = statsText;
}

function setChip(kind, text) {
  const chip = $("status-chip");
  chip.className = "chip " + kind;
  chip.textContent = text;
}

function showHu(workItem) {
  $("card-hu").classList.remove("hidden");
  $("hu-output").textContent =
    `ID: ${workItem.id}\n` +
    `Título: ${workItem.title}\n` +
    `Estado: ${workItem.state}\n` +
    `Creado por: ${workItem.created_by}\n\n` +
    `Descripción:\n${workItem.description || "(sin descripción)"}\n\n` +
    `Criterios de aceptación:\n${workItem.acceptance_criteria || "(sin criterios)"}`;
}

function renderCoverage() {
  const box = $("coverage");
  box.innerHTML = "";
  const hurs = Object.entries(state.huMap);
  if (!hurs.length) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");

  hurs.forEach(([huId, hu]) => {
    const cases = state.testCases.filter((c) => c.work_item_id === Number(huId));
    const block = document.createElement("div");
    block.className = "coverage-hu";
    const head = document.createElement("h3");
    head.textContent = `Cobertura HU #${huId} — ${hu.title}`;
    block.appendChild(head);

    (hu.criteriaList || []).forEach((crit, idx) => {
      const n = idx + 1;
      const covering = cases.filter((c) => (c.criterios || []).includes(n)).length;
      const row = document.createElement("div");
      row.className = covering > 0 ? "cov-covered" : "cov-missing";
      row.textContent = `${covering > 0 ? "✔" : "✖"} ${n}. ${crit}  —  ${covering} caso${covering === 1 ? "" : "s"}`;
      block.appendChild(row);
    });

    if (!hu.criteriaList || !hu.criteriaList.length) {
      const row = document.createElement("div");
      row.className = "cov-muted";
      row.textContent = "(esta HU no tiene criterios de aceptación definidos)";
      block.appendChild(row);
    }
    box.appendChild(block);
  });
}

function renderCases(cases) {
  const container = $("cases-container");
  container.innerHTML = "";
  cases.forEach((tc, idx) => container.appendChild(renderCase(tc, idx)));
}

function renderCase(tc, idx) {
  const div = document.createElement("div");
  div.className = "case";
  div.dataset.index = idx;

  const head = document.createElement("div");
  head.className = "case-head";

  const label = document.createElement("span");
  label.className = "case-label";
  label.textContent = `Test Case ${idx + 1}`;

  const huBadge = tc.work_item_id
    ? (() => {
        const b = document.createElement("span");
        b.className = "hu-badge";
        b.textContent = `HU #${tc.work_item_id}`;
        b.title = "Historia de Usuario de origen";
        return b;
      })()
    : null;

  const title = document.createElement("input");
  title.className = "case-title";
  title.value = tc.title;
  title.placeholder = "Título";
  title.addEventListener("input", () => { tc.title = title.value; });

  const priority = document.createElement("select");
  priority.className = "case-priority";
  [1, 2, 3, 4].forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = `P${p}`;
    opt.selected = Number(tc.priority) === p;
    priority.appendChild(opt);
  });
  priority.addEventListener("change", () => { tc.priority = Number(priority.value); });

  const type = document.createElement("select");
  type.className = "case-type";
  ["funcional", "regresion", "integracion", "usabilidad", "rendimiento", "seguridad"].forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    opt.selected = tc.type === t;
    type.appendChild(opt);
  });
  type.addEventListener("change", () => { tc.type = type.value; });

  const delCase = document.createElement("button");
  delCase.className = "case-del";
  delCase.textContent = "✕";
  delCase.title = "Eliminar caso";
  delCase.addEventListener("click", () => {
    state.testCases.splice(idx, 1);
    renderCases(state.testCases);
  });

  head.append(label, title, priority, type, delCase);
  if (huBadge) head.appendChild(huBadge);
  div.appendChild(head);

  const desc = document.createElement("textarea");
  desc.className = "case-pre";
  desc.placeholder = "Descripción";
  desc.value = tc.description || "";
  desc.addEventListener("input", () => { tc.description = desc.value; });
  div.appendChild(desc);

  const pre = document.createElement("textarea");
  pre.className = "case-pre";
  pre.placeholder = "Precondiciones";
  pre.value = tc.preconditions;
  pre.addEventListener("input", () => { tc.preconditions = pre.value; });
  div.appendChild(pre);

  const crit = document.createElement("input");
  crit.className = "case-crit";
  crit.placeholder = "Criterios de aceptación que cubre (ej. 1,3)";
  crit.value = (tc.criterios || []).join(", ");
  crit.addEventListener("input", () => {
    tc.criterios = crit.value.split(",").map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n));
    renderCoverage();
  });
  div.appendChild(crit);

  tc.steps.forEach((step, i) => div.appendChild(renderStep(tc, step, i)));

  const addBtn = document.createElement("button");
  addBtn.className = "add-step";
  addBtn.textContent = "+ Agregar paso";
  addBtn.addEventListener("click", () => {
    tc.steps.push({ action: "", expected: "" });
    renderCases(state.testCases);
  });
  div.appendChild(addBtn);

  return div;
}

function renderStep(tc, step, i) {
  const row = document.createElement("div");
  row.className = "step-row";

  const action = document.createElement("input");
  action.className = "step-input";
  action.placeholder = "Acción";
  action.value = step.action;
  action.addEventListener("input", () => { step.action = action.value; });

  const expected = document.createElement("input");
  expected.className = "step-input";
  expected.placeholder = "Resultado esperado";
  expected.value = step.expected;
  expected.addEventListener("input", () => { step.expected = expected.value; });

  const del = document.createElement("button");
  del.className = "step-del";
  del.textContent = "✕";
  del.addEventListener("click", () => {
    tc.steps.splice(i, 1);
    renderCases(state.testCases);
  });

  row.append(action, expected, del);
  return row;
}

async function generate() {
  const raw = $("work-item-id").value.trim();
  if (!raw) { alert("Ingresa al menos un ID de HU"); return; }
  const ids = [...new Set(raw.split(/[\s,;]+/).filter(Boolean))].slice(0, 20);
  const quantity = Number($("quantity").value) || 5;
  const instructions = $("instructions").value.trim();

  state = { workItem: null, testCases: [], huMap: {} };
  $("card-hu").classList.add("hidden");
  $("card-results").classList.add("hidden");
  $("create-result").textContent = "";

  for (let i = 0; i < ids.length; i++) {
    const id = ids[i];
    setLoading(true, ids.length > 1
      ? `Generando HU #${id} (${i + 1}/${ids.length})… puede tardar unos minutos`
      : "Generando con el modelo local… puede tardar unos minutos");
    await streamOne(id, quantity, instructions);
  }
  setLoading(false);

  if (!state.testCases.length) {
    setChip("chip-err", "error");
    return;
  }
  renderResults();
  setChip("chip-ok", "conectado");
}

function streamOne(id, quantity, instructions) {
  return new Promise((resolve) => {
    const url = `/api/generate-stream?work_item_id=${id}&quantity=${quantity}&instructions=${encodeURIComponent(instructions)}`;
    const es = new EventSource(url);

    es.addEventListener("start", () => {
      setProgress(2, `Conectando HU #${id}…`);
    });

    es.addEventListener("progress", (e) => {
      const d = JSON.parse(e.data);
      setProgress(
        d.percent,
        `HU #${id} · Tokens: ${d.tokens} / ~${d.estimated} · ${d.tokens_per_sec}/s · ${d.elapsed}s`
      );
    });

    es.addEventListener("done", (e) => {
      const d = JSON.parse(e.data);
      es.close();
      const wi = d.work_item;
      state.workItem = wi;
      state.huMap[wi.id] = { title: wi.title, criteriaList: wi.criteria_list || [] };
      d.test_cases.forEach((tc) => {
        tc.work_item_id = wi.id;
        tc.criterios = tc.criterios || [];
        state.testCases.push(tc);
      });
      resolve();
    });

    es.addEventListener("error", (e) => {
      es.close();
      let msg = "No se pudo conectar con el servidor de generación.";
      if (e.data) {
        try { msg = JSON.parse(e.data).detail; } catch { /* ignore */ }
      }
      alert(`HU #${id}: ${msg}`);
      resolve();
    });
  });
}

function renderResults() {
  showHu(state.workItem);
  $("summary").textContent = state.testCases.length + " casos en " + Object.keys(state.huMap).length + " HU";
  renderCoverage();
  renderCases(state.testCases);
  $("card-results").classList.remove("hidden");
}

async function fetchHu() {
  const workItemId = $("work-item-id").value.trim();
  if (!workItemId) { alert("Ingresa el ID de la HU"); return; }
  setLoading(true);
  try {
    const data = await api(`/api/hu/${workItemId}`);
    state.workItem = data;
    showHu(state.workItem);
    setChip("chip-ok", "conectado");
  } catch (err) {
    setChip("chip-err", "error");
    alert(err.message);
  } finally {
    setLoading(false);
  }
}

async function createCases() {
  if (!state.testCases.length) { alert("Primero genera casos"); return; }
  setLoading(true, "Creando test cases en Azure DevOps…");

  const groups = {};
  state.testCases.forEach((tc) => {
    const k = tc.work_item_id || (state.workItem && state.workItem.id) || 0;
    (groups[k] = groups[k] || []).push(tc);
  });

  const allCreated = [];
  let err = null;
  let demo = false;
  for (const [huId, cases] of Object.entries(groups)) {
    try {
      const data = await api("/api/create", {
        method: "POST",
        body: JSON.stringify({ work_item_id: Number(huId), test_cases: cases }),
      });
      allCreated.push(...(data.created || []));
      if (data.demo) demo = true;
      if (data.error) err = data.error;
    } catch (e) {
      err = e.message;
      break;
    }
  }
  setLoading(false);

  const links = allCreated
    .map((c) => (c.url ? `<a href="${c.url}" target="_blank" rel="noopener">#${c.id}</a>` : `#${c.id}`))
    .join(", ");
  $("create-result").innerHTML = demo
    ? `MODO DEMO: no se insertó en Azure. Se enviarían ${allCreated.length} test cases: ${allCreated.map((c) => `#${c.id}`).join(", ")}`
    : err
    ? `Se crearon ${allCreated.length} y falló en: ${err}`
    : `Creados ${allCreated.length} test cases en Azure DevOps: ${links}`;
  setChip("chip-ok", demo ? "demo" : "conectado");
}

function addCaseManual() {
  const huId = state.workItem && state.workItem.id;
  state.testCases.push({
    title: "",
    description: "",
    priority: 2,
    type: "funcional",
    preconditions: "",
    criterios: [],
    work_item_id: huId,
    steps: [{ action: "", expected: "" }],
  });
  renderCases(state.testCases);
  renderCoverage();
  $("card-results").classList.remove("hidden");
}

function reset() {
  state = { workItem: null, testCases: [], huMap: {} };
  $("card-hu").classList.add("hidden");
  $("card-results").classList.add("hidden");
  $("create-result").textContent = "";
  $("summary").textContent = "";
}

const PRESETS = {
  smoke: "Genera casos smoke que validen el flujo principal de la HU (camino feliz).",
  regresion: "Enfócate en casos de regresión: validar que funcionalidades existentes no se rompan.",
  seguridad: "Enfócate en casos de seguridad: autenticación, autorización, inyección y datos sensibles.",
  usabilidad: "Enfócate en casos de usabilidad y experiencia de usuario.",
};

function applyPreset(name) {
  $("instructions").value = name === "clear" ? "" : PRESETS[name];
}

$("btn-generate").addEventListener("click", generate);
$("btn-fetch-hu").addEventListener("click", fetchHu);
$("btn-add-case").addEventListener("click", addCaseManual);
$("btn-create").addEventListener("click", createCases);
$("btn-reset").addEventListener("click", reset);

document.querySelectorAll(".preset-btn").forEach((b) => {
  b.addEventListener("click", () => applyPreset(b.dataset.preset));
});

(async function init() {
  try {
    const h = await api("/api/health");
    setChip("chip-ok", h.demo_mode ? "demo" : `ok · ${h.model}`);
    if (h.demo_mode) {
      $("demo-banner").classList.remove("hidden");
    }
  } catch {
    setChip("chip-err", "sin conexión");
  }
})();