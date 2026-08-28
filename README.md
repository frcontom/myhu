# QA Test Case Generator

Genera casos de prueba automáticamente a partir de una Historia de Usuario de Azure DevOps usando un LLM local (Ollama en Docker). Los casos generados pueden crearse directamente como work items `Test Case` enlazados a la HU.

## Arquitectura

```
┌─────────────┐   REST    ┌──────────────────┐   HTTP    ┌─────────┐
│  Frontend   │ ────────► │  Backend FastAPI  │ ────────► │ Ollama  │
│ (HTML/JS)   │ ◄──────── │ (Docker)         │ ◄──────── │ (LLM)   │
└─────────────┘           └────────┬─────────┘           └─────────┘
                                   │ REST + PAT
                                   ▼
                        Azure DevOps API
```

## Requisitos

- Docker Desktop en Windows.
- Un PAT de Azure DevOps con permisos **Work Items → Read & Write**.

## Montaje (3 pasos)

### 1. Crear el `.env`

```powershell
Copy-Item .env.example .env
```

Edita `.env` con el Bloc de notas y reemplaza **solo los valores** (no borres los nombres de las variables). Mientras estén los valores plantilla, la app corre en **modo demo**.

### Cómo llenar los valores de Azure DevOps

| Variable | Qué poner | Dónde lo encuentro |
|----------|-----------|--------------------|
| `AZURE_DEVOPS_ORG` | Nombre de la organización, **sin** `https://` | Es lo que sale en `https://dev.azure.com/<ESTO>`. Ej: `dev.azure.com/miempresa` → `AZURE_DEVOPS_ORG=miempresa` |
| `AZURE_DEVOPS_PROJECT` | Nombre **exacto** del proyecto | Aparece al lado del logo cuando abres tu proyecto en el portal |
| `AZURE_DEVOPS_PAT` | Tu Personal Access Token | Ver pasos abajo |

**Crear el PAT (Personal Access Token):**
1. Entra a `https://dev.azure.com/<tu-org>/_usersSettings/tokens`.
2. Clic en **+ New Token** → Nombre: `qa-testcase-generator`.
3. **Organization**: tu organización.
4. **Scopes**: expande **Work Items** y marca **Read & Write**.
5. **Expiration**: 30 o 90 días.
6. Clic en **Create** → **copia el token** (solo se muestra una vez) y pégalo en `AZURE_DEVOPS_PAT` sin comillas ni espacios.

Ejemplo de `.env` ya llenado:
```
AZURE_DEVOPS_ORG=miempresa
AZURE_DEVOPS_PROJECT=Proyecto QA
AZURE_DEVOPS_PAT=xy7abcdefghijklmnopqrstuvwxyz1234567890
```

Después de guardar, reinicia con `docker compose up -d --build`. Si el banner amarillo "MODO DEMO" desaparece, estás conectado a Azure real.

### 2. Levantar

```powershell
docker compose up -d --build
```

La primera vez descargará e instalará el modelo de Ollama (~4.7 GB para 7b). El backend espera a que el modelo esté listo; si hace falta, ejecuta manualmente:

```powershell
docker exec -it qa-testcase-ollama ollama pull qwen2.5:7b-instruct
```

> El modelo configurado en `.env` debe estar descargado en Ollama (`docker exec -it qa-testcase-ollama ollama list`).

### 3. Abrir

Ve a **http://localhost:8000**

## Uso

1. Ingresa el **ID de la HU**.
2. Define la **cantidad** de casos esperada.
3. Opcional: instrucciones extra (ej. "enfócate en negativos y seguridad").
4. **Generar casos de prueba** → el agente lee la HU de Azure y el LLM local devuelve los casos.
5. Revisa/edita cada caso (título, descripción, precondiciones, pasos).
6. **Crear en Azure DevOps** → crea los `Test Case` enlazados a la HU (aparecerán en la pestaña "Tested by" de la HU y en Test Plans).

## Modo demo (sin Azure DevOps)

Si no configuras `AZURE_DEVOPS_*` en el `.env`, el sistema entra en **modo demo**:

- Se usa una Historia de Usuario de ejemplo ("Inicio de sesión de usuario").
- La generación de casos con el LLM local funciona igual.
- El botón "Crear en Azure DevOps" **simula** la creación (no inserta nada en Azure) y lo indica en el resultado.

Es ideal para probar la herramienta antes de tener el PAT o para hacer demos.

## Velocidad y barra de progreso

- La generación es **lenta a propósito**: el modelo corre en CPU (sin GPU) y genera texto token a token. Un caso con varios pasos puede tardar ~30-60 s; 5 casos ~2-5 min.
- Mientras genera, el front muestra una **barra de progreso en vivo** con tokens generados, velocidad (tokens/s) y tiempo transcurrido (streaming vía SSE).
- **Consejos para acelerar** (editar `.env` y `docker compose up -d`):
  - Cambiar `OLLAMA_MODEL=qwen2.5:3b-instruct` → ~2-3x más rápido (algo menos calidad). El 7b es el recomendado por calidad.
  - Pedir menos casos por petición (los casos se pueden seguir agregando manualmente en el editor).
  - El modelo queda cargado en RAM tras la primera generación (keep-alive 30 min), así que las siguientes son más rápidas.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Estado del servicio y modelo |
| GET | `/api/hu/{id}` | Obtiene la HU de Azure DevOps |
| POST | `/api/generate` | Genera casos con el LLM (`work_item_id`, `quantity`, `instructions`) |
| POST | `/api/create` | Crea los test cases en Azure DevOps enlazados a la HU |

## Notas

- El PAT nunca sale del contenedor; se lee desde `.env` (no versionado).
- La conexión a Azure DevOps usa la REST API `api-version=7.1`.
- Para cambiar de modelo solo edita `OLLAMA_MODEL` en `.env` y ejecuta `docker compose up -d`.