# AGENTS.md — Contexto para IA que continúe este proyecto

Este archivo está pensado para que **cualquier IA** (ChatGPT, Claude, Gemini, opencode, etc.) entienda el proyecto y pueda continuar el desarrollo sin romper nada.

## Qué es el proyecto

**QA Test Case Generator** es una herramienta local para QA que genera casos de prueba a partir de una **Historia de Usuario (HU) de Azure DevOps**, usando un **LLM local (Ollama en Docker)**. Los casos generados pueden crearse automáticamente como work items `Test Case` en Azure DevOps, **enlazados a la HU** (relación `Tests` → aparece en "Tested by").

Todo corre en local con Docker Compose. Sin Node, sin base de datos, sin servicio externo.

## Stack

- **Backend:** Python 3.12 + FastAPI + httpx + pydantic-settings
- **Frontend:** HTML/CSS/JS vanilla servido por FastAPI (sin build)
- **LLM:** Ollama (contenedor `ollama/ollama`) con modelo `qwen2.5:7b-instruct` por defecto
- **Azure DevOps:** REST API `api-version=7.1`, autenticación con PAT (Basic auth)

## Cómo correr el proyecto

```powershell
Copy-Item .env.example .env   # completar AZURE_DEVOPS_ORG / PROJECT / PAT
docker compose up -d --build  # la primera vez baja ~4.7 GB del modelo
# abrir http://localhost:8000
```

- La primera descarga del modelo tarda. El backend intentará generar aunque el modelo no esté listo; si falla: `docker exec -it qa-testcase-ollama ollama pull qwen2.5:7b-instruct`.
- El PAT se lee del `.env` (nunca versionar). El `.env` NO debe commitearse.
- Para cambiar de modelo: editar `OLLAMA_MODEL` en `.env` y `docker compose up -d`.

## Estructura del proyecto

```
azureDevops/
├── docker-compose.yml        # servicios: backend (FastAPI) + ollama
├── .env.example              # plantilla de configuración
├── .env                      # configuración real (NO versionado)
├── .gitignore
├── README.md                 # guía de usuario (montaje + uso)
├── AGENTS.md                 # este archivo
├── docs/
│   ├── ARQUITECTURA.md       # detalle técnico (flujo, API, formato TCM)
│   └── ROADMAP.md            # estado y próximos pasos
└── backend/
    ├── Dockerfile            # python:3.12-slim + uvicorn
    ├── requirements.txt
    ├── app/
    │   ├── config.py         # Settings (pydantic-settings) lee de .env
    │   ├── azure_client.py   # cliente REST Azure DevOps (PAT + Basic auth)
    │   ├── llm_client.py     # prompt builder, cliente Ollama, parseo JSON, HTML TCM
    │   └── main.py           # FastAPI: rutas /api/* y sirve el front
    └── static/               # frontend vanilla
        ├── index.html
        ├── style.css
        └── app.js
```

## Flujo de datos (importante entender)

1. **Front** (`app.js`) envía `POST /api/generate` con `{work_item_id, quantity, instructions}`.
2. **Backend** (`azure_client.get_work_item`) consulta la HU en Azure DevOps: `GET .../_apis/wit/workitems/{id}?api-version=7.1&$expand=Relations`.
3. `llm_client.build_prompt` arma el prompt (español) con título, descripción y criterios de aceptación de la HU + las instrucciones del QA.
4. `llm_client.generate_test_cases` llama a Ollama (`POST {ollama_url}/api/generate`) con `format="json"` y parsea la respuesta (robusto: tolera markdown o JSON embebido).
5. El front muestra los casos en una tabla **editable** (título, prioridad, tipo, precondiciones, pasos).
6. **Front** envía `POST /api/create` con `{work_item_id, test_cases[]}`.
7. `azure_client.create_test_case` crea cada work item `$Test Case` con `Microsoft.VSTS.TCM.Steps` (HTML) y una relación `Microsoft.VSTS.Common.Tests` hacia la HU.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Estado, modelo, `azure_configured`, `demo_mode` |
| GET | `/api/test-azure` | Valida org + PAT + proyecto + permisos Work Items (botón "Probar conexión Azure") |
| GET | `/api/hu/{id}` | HU normalizada (incluye `criteria_list`) |
| GET | `/api/generate-stream` | Generación con streaming SSE (progreso en vivo) |
| POST | `/api/generate` | Generación bloqueante |
| POST | `/api/create` | Crea Test Cases en Azure enlazados a la HU |

## Flujo "Pasar a GPT" (sin API de OpenAI)

El usuario tiene ChatGPT **plan GO** (sin API). El flujo es manual: el front exporta un `.md` (`casos_para_gpt.md`) con HU + casos + plantilla "Hacking QA" embebida + bloque ```` ```json ```` reimportable. El usuario pega el archivo en ChatGPT, mejora los casos, y **re-importa** la respuesta. El import (`parseImportText` en `app.js`) prefiere el bloque JSON, luego JSON completo, luego parseo de markdown (`## Caso N` + etiquetas). No hay backend involucrado en esto (todo frontend).

## Puntos críticos del código (no romper)

- **`azure_client.py:23`**: auth Basic con usuario vacío → `base64(":PAT")`. Formato obligatorio.
- **`azure_client.py:86`**: la URL del work item es `/_apis/wit/workItems/{id}` y el POST va a `/wit/workitems/$Test Case` (con `$` URL-encoded). El `$` en la ruta debe escribirse `$Test Case`; httpx lo codifica.
- **`azure_client.py:79`**: la relación usa `rel: "Microsoft.VSTS.Common.TestedBy-Reverse"`. ⚠️ Es el nombre **direccional** que Azure acepta para el enlace "Tests"/"Tested by" (el caso queda en la pestaña "Tested by" de la HU). Los nombres base `Microsoft.VSTS.Common.Tests` / `Microsoft.VSTS.Common.TestedBy` dan 400 "Unknown relation type"; `System.LinkTypes.Related` siempre funciona pero no es "Tested by".
- **`llm_client.py`**: `format="json"` en Ollama fuerza JSON, pero igual se normaliza con `_parse_json` y `_normalize_case`. Nunca confiar en que el modelo devuelva JSON perfecto.
- **`llm_client.py:147` `steps_to_tcm_html`**: el formato HTML de pasos de Azure DevOps es `id` par/impar (Action + ExpectedResult), `last="{len(steps)*2}"`, y hay que escapar HTML (`_escape_html`).
- **`main.py:108`**: `StaticFiles(html=True)` montado en `/`; las rutas `/api/*` se registran ANTES para que el mount no las intercepte.
- El front usa IDs de elementos por `document.getElementById`, sin framework; el estado vive en la variable global `state` de `app.js`.

## Convenciones

- **Código en inglés, UI/prompts en español** (el usuario final es QA hispanohablante).
- **No agregar comentarios** salvo que sean necesarios para aclarar algo no evidente (los existentes marcan puntos críticos).
- Excepciones propias del dominio: `AzureDevOpsError`, `LLMError`, `TestCaseGenerationError`. El backend las traduce a `HTTPException` (502 con detalle legible).
- Manejar siempre errores de red/modelo y devolver `detail` entendible; el front muestra `alert(err.message)`.
- No agregar dependencias sin necesidad; el stack actual es mínimo a propósito (rápido y fácil de montar en local).

## Validación / QA del código

- Sintaxis Python (sin deps): `python -m py_compile backend\app\*.py` (desde la raíz).
- Compose válido: `docker compose config --quiet` (desde la raíz).
- NOTA: el PC del usuario tiene **Python 3.14** y pydantic-core no tiene wheels → NO instalar deps localmente; todo se prueba en Docker (imagen `python:3.12-slim`).
- No hay suite de tests automatizada todavía (ver `docs/ROADMAP.md`).

## Errores comunes y troubleshooting

| Problema | Causa / solución |
|----------|------------------|
| `/api/generate` → 502 "No se pudo conectar con Ollama" | El contenedor `ollama` aún no está listo o el modelo no está descargado. `docker exec -it qa-testcase-ollama ollama list`; si falta, `ollama pull qwen2.5:7b-instruct`. |
| 502 "Azure DevOps GET ... HTTP 401" | PAT incorrecto o sin permisos `Work Items → Read & Write`. Revisar `.env`. |
| 502 "HTTP 404" al crear Test Case | Org/proyecto mal escrito en `.env`, o el PAT no tiene acceso al proyecto. |
| 400 "Configura AZURE_DEVOPS_*" | Falta crear/completar `.env` y reiniciar el contenedor (`docker compose up -d`). |
| El modelo devuelve casos mal formados | Bajar temperatura (`OLLAMA_TEMPERATURE=0.2`), subir `OLLAMA_MAX_TOKENS`, o cambiar a un modelo mayor si la RAM lo permite. |
| RAM insuficiente | PC del usuario tiene ~7 GB libres → `qwen2.5:7b` es el tope cómodo. Modelos alternativos en `README.md`. |

## Reglas para la IA que continúe

1. Leer `docs/ARQUITECTURA.md` y `docs/ROADMAP.md` antes de tocar código.
2. **Nunca** escribir ni versionar el `.env` real con el PAT.
3. No introducir frameworks frontend ni bases de datos sin confirmar con el usuario (la premisa es "rápido y fácil de montar").
4. Si tocas `steps_to_tcm_html` o el formato de relaciones, probar contra Azure DevOps real o documentar el cambio.
5. Los cambios deben mantener el flujo actual: leer HU → generar con LLM local → revisar → crear en Azure.