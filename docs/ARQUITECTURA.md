# ARQUITECTURA

Detalle técnico del **QA Test Case Generator**.

## Visión general

Sistema local de 2 contenedores Docker:

| Contenedor | Imagen | Rol |
|------------|--------|-----|
| `backend` | `python:3.12-slim` + uvicorn | API FastAPI, orquesta HU→LLM→Azure |
| `ollama` | `ollama/ollama` | Servidor LLM local (modelo qwen2.5:7b-instruct) |

El frontend es servido por FastAPI (static files). No hay Node, ni DB, ni servicio externo salvo Azure DevOps.

## Flujo de datos

```
app.js ──POST /api/generate──► main.generate()
                                   │
                                   ├─ azure_client.get_work_item(id) ──► Azure DevOps GET /_apis/wit/workitems/{id}
                                   │
                                   ├─ llm_client.generate_test_cases(work_item, qty, instructions)
                                   │       └─ build_prompt() → Ollama POST /api/generate (format=json)
                                   │
                                   └─ return { work_item, summary, test_cases[] }  →  front (tabla editable)

app.js ──POST /api/create──► main.create()
                                   ├─ steps_to_tcm_html(steps)  (formato TCM de Azure)
                                   └─ azure_client.create_test_case(title, steps_html, hu_id)
                                           └─ POST /_apis/wit/workitems/$Test Case (JSON Patch)
                                                + relation Microsoft.VSTS.Common.Tests → HU
```

## API

| Método | Ruta | Body | Respuesta |
|--------|------|------|-----------|
| GET | `/api/health` | — | `{status, model, azure_configured, demo_mode, ollama_url}` |
| GET | `/api/test-azure` | — | `{ok, report{org_ok,pat_ok,project_found,wit_access_ok}, error, message}` (valida conexión) |
| GET | `/api/hu/{id}` | — | HU normalizada `{id, type, title, description, acceptance_criteria, criteria_list, state, created_by}` |
| POST | `/api/generate` | `{work_item_id, quantity(1-50), instructions}` | `{work_item, summary, test_cases[]}` (bloqueante) |
| GET | `/api/generate-stream` | query params | **SSE**: `start` → `progress*` → `done` / `error` |
| POST | `/api/create` | `{work_item_id, test_cases[]}` | `{created[], count, linked_to_work_item}` (o `{created, error}` si falla a mitad) |

### Streaming SSE (`/api/generate-stream`)

La generación usa `stream: True` de Ollama y se proxya al front como Server-Sent Events:

- `event: start` → `{estimated_tokens}`
- `event: progress` → `{tokens, elapsed, tokens_per_sec, percent, estimated}` (aprox. cada 0.25 s)
- `event: done` → `{summary, test_cases[], work_item}` (incluye la HU resuelta)
- `event: error` → `{detail}`

El front consume con `EventSource` y pinta la barra de progreso en vivo (`app.js:generate`). La estimación de `percent` usa `AVG_TOKENS_PER_CASE=400` en `llm_client.py`.

### Formato de un test case (API + front)

```json
{
  "title": "TC-001: ...",
  "description": "descripción breve del caso",
  "priority": 1,
  "type": "funcional",
  "preconditions": "...",
  "criterios": [1, 3],
  "steps": [{"action": "...", "expected": "..."}]
}
```

- La `description` se guarda en el campo `System.Description` del Test Case.
- La `priority` se guarda en `Microsoft.VSTS.Common.Priority` (desde `main.py:create`).
- Los pasos son pares `action` (Acción) + `expected` (Resultado esperado); en el front se editan como inputs.
- El `type` no se envía a Azure (el Test Case no tiene ese campo estándar); es solo organizativo en el editor.
- `criterios` referencia índices (1-based) de `criteria_list` de la HU; alimenta el panel de cobertura.

## Integración Azure DevOps

- **Auth:** `Authorization: Basic base64(":PAT")` (usuario vacío, el PAT como password). `azure_client.py:23`.
- **API version:** `api-version=7.1`.
- **Leer HU:** `GET {base}/{project}/_apis/wit/workitems/{id}?api-version=7.1&$expand=Relations`. Se extraen `System.Title`, `System.Description`, `Microsoft.VSTS.Common.AcceptanceCriteria`, `System.State`, `System.WorkItemType`.
- **Crear Test Case:** `POST {base}/{project}/_apis/wit/workitems/$Test Case` con `Content-Type: application/json-patch+json` y un JSON Patch:
  - `add /fields/System.Title`
  - `add /fields/System.Description` (opcional)
  - `add /fields/Microsoft.VSTS.TCM.Steps` (HTML de pasos)
  - `add /relations/-` con `{rel: "Microsoft.VSTS.Common.Tests", url: "<url de la HU>"}`.

### Formato TCM.Steps (HTML)

```html
<steps id="0" last="4">
  <step id="1" type="Action"><parameterizedString>A1</parameterizedString><description/></step>
  <step id="2" type="ExpectedResult"><parameterizedString>E1</parameterizedString><description/></step>
  <step id="3" type="Action"><parameterizedString>A2</parameterizedString><description/></step>
  <step id="4" type="ExpectedResult"><parameterizedString>E2</parameterizedString><description/></step>
</steps>
```

- `last = len(steps) * 2`.
- ids correlativos: impar = Action, par = ExpectedResult.
- Todo texto debe ir escapado (`& < > "`).
- Generado por `llm_client.steps_to_tcm_html`.

## Integración Ollama

- **Endpoint:** `POST {ollama_url}/api/generate`, `stream: false`, `format: "json"`.
- **Options:** `temperature` (0.2) y `num_predict` (8192) desde `config`.
- **Timeouts largos** (600s) porque el 7b en CPU puede tardar varios minutos con 5+ casos.
- **Parseo robusto** (`_parse_json`): tolera bloques markdown ```json y JSON embebido en texto; si falla, lanza `TestCaseGenerationError`.

## Configuración (config.py / .env)

| Variable | Default | Uso |
|----------|---------|-----|
| `AZURE_DEVOPS_ORG` | — | Org de Azure (sin https) |
| `AZURE_DEVOPS_PROJECT` | — | Proyecto |
| `AZURE_DEVOPS_PAT` | — | Token (Basic auth) |
| `OLLAMA_URL` | `http://ollama:11434` | Host del contenedor ollama |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Modelo a usar |
| `OLLAMA_TEMPERATURE` | `0.2` | Determinismo |
| `OLLAMA_MAX_TOKENS` | `8192` | Tope de generación |

## Notas de entorno (PC del usuario)

- RAM libre ~7 GB → modelo máximo cómodo: `qwen2.5:7b-instruct` (~4.7 GB).
- Python local 3.14 sin wheels de pydantic-core → nunca instalar deps en el host; todo se prueba dentro de Docker.
- Docker Desktop instalado y funcionando.