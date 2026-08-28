const $ = (id) => document.getElementById(id);

let state = {
  workItem: null,
  testCases: [],
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

function setLoading(on) {
  $("loader").classList.toggle("hidden", !on);
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
  const workItemId = $("work-item-id").value.trim();
  if (!workItemId) { alert("Ingresa el ID de la HU"); return; }

  const payload = {
    work_item_id: Number(workItemId),
    quantity: Number($("quantity").value) || 5,
    instructions: $("instructions").value.trim(),
  };

  setLoading(true);
  try {
    const data = await api("/api/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.workItem = data.work_item;
    state.testCases = data.test_cases;
    showHu(state.workItem);
    $("summary").textContent = data.summary || "";
    renderCases(state.testCases);
    $("card-results").classList.remove("hidden");
    setChip("chip-ok", "conectado");
  } catch (err) {
    setChip("chip-err", "error");
    alert(err.message);
  } finally {
    setLoading(false);
  }
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
  if (!state.workItem || !state.testCases.length) { alert("Primero genera casos"); return; }
  setLoading(true);
  try {
    const data = await api("/api/create", {
      method: "POST",
      body: JSON.stringify({
        work_item_id: state.workItem.id,
        test_cases: state.testCases,
      }),
    });
    const ok = data.created.map((c) => `#${c.id}`).join(", ");
    $("create-result").textContent = data.error
      ? `Se crearon ${data.created.length} y falló en: ${data.error}`
      : `Creados ${data.count} test cases en Azure DevOps: ${ok} (enlazados a la HU #${state.workItem.id})`;
    setChip("chip-ok", "conectado");
  } catch (err) {
    setChip("chip-err", "error");
    alert(err.message);
  } finally {
    setLoading(false);
  }
}

function addCaseManual() {
  state.testCases.push({
    title: "",
    description: "",
    priority: 2,
    type: "funcional",
    preconditions: "",
    steps: [{ action: "", expected: "" }],
  });
  renderCases(state.testCases);
  $("card-results").classList.remove("hidden");
}

function reset() {
  state = { workItem: null, testCases: [] };
  $("card-hu").classList.add("hidden");
  $("card-results").classList.add("hidden");
  $("create-result").textContent = "";
  $("summary").textContent = "";
}

$("btn-generate").addEventListener("click", generate);
$("btn-fetch-hu").addEventListener("click", fetchHu);
$("btn-add-case").addEventListener("click", addCaseManual);
$("btn-create").addEventListener("click", createCases);
$("btn-reset").addEventListener("click", reset);

(async function init() {
  try {
    const h = await api("/api/health");
    setChip("chip-ok", `ok · ${h.model}`);
  } catch {
    setChip("chip-err", "sin conexión");
  }
})();