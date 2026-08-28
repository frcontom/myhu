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

    let warmSec = 0;
    const ticker = setInterval(() => {
      warmSec += 1;
      setProgress(
        Math.min(2 + warmSec / 3, 20),
        `Cargando modelo para HU #${id}… ${warmSec}s (primera vez hasta 1 min)`
      );
    }, 1000);

    es.addEventListener("start", () => {
      setProgress(2, `Cargando modelo para HU #${id}… primera vez puede tardar hasta 1 min`);
    });

    es.addEventListener("progress", (e) => {
      clearInterval(ticker);
      const d = JSON.parse(e.data);
      setProgress(
        d.percent,
        `HU #${id} · Tokens: ${d.tokens} / ~${d.estimated} · ${d.tokens_per_sec}/s · ${d.elapsed}s`
      );
    });

    es.addEventListener("done", (e) => {
      clearInterval(ticker);
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
      clearInterval(ticker);
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
    state.huMap[data.id] = { title: data.title, criteriaList: data.criteria_list || [] };
    showHu(state.workItem);
    const card = $("card-hu");
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    card.classList.remove("flash");
    void card.offsetWidth;
    card.classList.add("flash");
    setChip("chip-ok", `HU #${data.id} cargada`);
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

const PLANTILLA_GPT = `Actúa como un QA Senior con más de 20 años de experiencia en testing funcional, backend, integración, seguridad y arquitectura de software.

Activa el modo "Hacking QA" y realiza un análisis profundo, crítico y estructurado de la historia de usuario de este archivo.

Trabaja con un enfoque profesional tipo ISTQB / QA Lead: pensamiento analítico, detección de riesgos y validación de reglas de negocio.

INSTRUCCIONES:
1. La Historia de Usuario está en la sección "# HISTORIA DE USUARIO" al inicio del archivo: úsala como FUENTE DE VERDAD para todo tu análisis (componentes funcionales, ambigüedades, riesgos y reglas de negocio implícitas).
2. Mejora los casos de prueba existentes y añade los que hagan falta (no genéricos, que detecten errores en producción).
3. Cada caso DEBE incluir: Título, Descripción (clara y profesional), Precondiciones SIEMPRE, Pasos, y Resultado Esperado por cada paso.
4. Formato de pasos: cada paso con su propio resultado esperado (nunca agrupar).
5. Cubre mínimo: happy path, validaciones, reglas de negocio, negativos importantes y escenarios críticos.
6. Lenguaje profesional listo para Jira/TestRail.
7. Al final incluye: Cobertura lograda y Riesgos detectados adicionales.
8. CONSERVA el identificador "## Caso N" y las etiquetas "- HU origen:/- Título:/- Descripción:/- Prioridad:/- Tipo:/- Precondiciones:/- Criterios que cubre:/- Pasos:" de cada caso. NO cambies el "- HU origen:" de ningún caso (indica la historia de usuario a la que pertenece).
9. Responde el JSON actualizado dentro del bloque \`\`\`json\`\`\` de la sección "JSON PARA REIMPORTAR" (es lo que la herramienta re-importará).`;

function flatten(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function huTitleFor(id) {
  if (!id) return "";
  const hu = state.huMap[id];
  if (hu) return hu.title;
  if (state.workItem && state.workItem.id === id) return state.workItem.title;
  return "";
}

function buildExportMd() {
  const lines = [];
  lines.push("# HISTORIA DE USUARIO");
  const hu = state.workItem;
  if (hu) {
    lines.push(`- ID: ${hu.id}`);
    lines.push(`- Título: ${flatten(hu.title)}`);
    lines.push(`- Tipo: ${flatten(hu.type)}`);
    lines.push(`- Descripción: ${flatten(hu.description)}`);
    lines.push(`- Criterios de aceptación: ${flatten(hu.acceptance_criteria)}`);
  } else {
    lines.push("- (no hay HU cargada)");
  }
  lines.push("");
  lines.push("# CASOS DE PRUEBA");
  state.testCases.forEach((tc, i) => {
    const huId = tc.work_item_id || (state.workItem && state.workItem.id);
    lines.push(`## Caso ${i + 1}`);
    lines.push(`- HU origen: #${huId} ${flatten(huTitleFor(huId))}`);
    lines.push(`- Título: ${flatten(tc.title)}`);
    lines.push(`- Descripción: ${flatten(tc.description)}`);
    lines.push(`- Prioridad: ${tc.priority}`);
    lines.push(`- Tipo: ${flatten(tc.type)}`);
    lines.push(`- Precondiciones: ${flatten(tc.preconditions)}`);
    lines.push(`- Criterios que cubre: ${(tc.criterios || []).join(", ")}`);
    lines.push("- Pasos:");
    (tc.steps || []).forEach((s, j) => {
      lines.push(`    ${j + 1}. ${flatten(s.action)} -> ${flatten(s.expected)}`);
    });
    lines.push("");
  });
  lines.push("---");
  lines.push("# INSTRUCCIONES PARA EL MODELO");
  lines.push(PLANTILLA_GPT);
  lines.push("");
  lines.push("# JSON PARA REIMPORTAR (responde aquí el JSON con los casos mejorados)");
  lines.push("```json");
  lines.push(JSON.stringify(state.testCases, null, 2));
  lines.push("```");
  return lines.join("\n");
}

function exportToGpt() {
  if (!state.testCases.length) { alert("Primero genera casos"); return; }
  const md = buildExportMd();
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "casos_para_gpt.md";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    document.body.removeChild(a);
  }, 1000);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(md).catch(() => {});
  }
  alert("Archivo descargado y copiado al portapapeles. Pégalo en ChatGPT, aplica la plantilla y vuelve con el archivo mejorado.");
}

function normalizeImported(raw) {
  return raw.map((r) => ({
    title: flatten(r.title),
    description: flatten(r.description),
    priority: Number(r.priority) || 2,
    type: (flatten(r.type).split("|")[0].trim()) || "funcional",
    preconditions: flatten(r.preconditions),
    criterios: Array.isArray(r.criterios)
      ? r.criterios.map((n) => Number(n)).filter((n) => !isNaN(n))
      : [],
    work_item_id: r.work_item_id || (state.workItem && state.workItem.id),
    steps: (r.steps || []).map((s) => ({
      action: flatten(s.action),
      expected: flatten(s.expected),
    })),
  }));
}

function parseMdCases(text) {
  const cases = [];
  let current = null;
  let inSteps = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (/^##\s+Caso/i.test(line)) {
      if (current) cases.push(current);
      current = { steps: [] };
      inSteps = false;
      continue;
    }
    if (!current) continue;
    const stepMatch = line.match(/^(\d+)\.\s+(.*?)\s*->\s*(.*)$/);
    if (stepMatch) {
      current.steps.push({ action: stepMatch[2].trim(), expected: stepMatch[3].trim() });
      inSteps = true;
      continue;
    }
    const kv = line.match(/^- ([^:]+):\s*(.*)$/);
    if (kv) {
      const key = kv[1].toLowerCase();
      const value = kv[2].trim();
      if (key === "pasos") { inSteps = true; continue; }
      inSteps = false;
      if (key === "título" || key === "titulo") current.title = value;
      else if (key === "descripción" || key === "descripcion") current.description = value;
      else if (key === "prioridad") current.priority = Number(value) || 2;
      else if (key === "tipo") current.type = value;
      else if (key === "precondiciones") current.preconditions = value;
      else if (key === "hu origen" || key === "hu") {
        const m = value.match(/#(\d+)/);
        if (m) current.work_item_id = Number(m[1]);
      }
      else if (key === "criterios que cubre") current.criterios = value.split(",").map((s) => Number(s.trim())).filter((n) => !isNaN(n));
      continue;
    }
    if (inSteps && line) {
      const last = current.steps.length;
      if (last > 0) {
        const lastStep = current.steps[last - 1];
        if (!lastStep.expected && !/->/.test(line)) {
          lastStep.expected = line;
        }
      }
    }
  }
  if (current) cases.push(current);
  return cases;
}

function parseImportText(text) {
  const jsonBlock = text.match(/```json\s*([\s\S]*?)```/i);
  if (jsonBlock) {
    const data = JSON.parse(jsonBlock[1]);
    const arr = Array.isArray(data) ? data : data.test_cases;
    if (Array.isArray(arr)) return normalizeImported(arr);
  }
  try {
    const data = JSON.parse(text);
    const arr = Array.isArray(data) ? data : data.test_cases;
    if (Array.isArray(arr)) return normalizeImported(arr);
  } catch { /* no es json */ }
  return normalizeImported(parseMdCases(text));
}

function importFromGpt() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".md,.json,.txt";
  input.onchange = () => {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const cases = parseImportText(String(reader.result));
        if (!cases.length) { alert("No se encontraron casos en el archivo."); return; }
        state.testCases = cases;
        if (!state.workItem) {
          state.workItem = {
            id: cases[0].work_item_id,
            title: "HU importada",
            type: "User Story",
            description: "",
            acceptance_criteria: "",
            criteria_list: [],
            state: "",
            created_by: "",
          };
        }
        renderResults();
        alert(`Se importaron ${cases.length} casos. Revisa el editor y luego crea en Azure DevOps.`);
      } catch (e) {
        alert("No se pudo importar el archivo: " + e.message);
      }
    };
    reader.readAsText(file);
  };
  input.click();
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
$("btn-export-gpt").addEventListener("click", exportToGpt);
$("btn-import-gpt").addEventListener("click", importFromGpt);
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