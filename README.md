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

- **Docker Desktop** en Windows (instalado y funcionando).
- Una **cuenta de Azure DevOps** (gratis, puede ser la misma de Outlook/Hotmail/Microsoft).
- Un **PAT** de Azure DevOps con permisos **Work Items → Read & Write** (ver Paso a paso abajo).

## Montaje (4 pasos)

### Paso 1. Crear el `.env`

```powershell
Copy-Item .env.example .env
```

Edita `.env` con el Bloc de notas y reemplaza **solo los valores** (nunca borres los nombres de las variables). Mientras estén los valores plantilla (`tu-organizacion`, `Tu-Proyecto`, `tu_pat_aqui`), la app corre en **modo demo** y NO crea nada en Azure.

---

## Paso a paso: de dónde sale cada dato del `.env`

### 1. `AZURE_DEVOPS_ORG` (la organización)

1. Entra a **https://dev.azure.com** e inicia sesión con tu cuenta Microsoft.
2. Fíjate en la **barra de direcciones**: `https://dev.azure.com/ESTO-ES-LA-ORG`.
3. **ORG = todo lo que va después de `dev.azure.com/`**, sin `https://`, sin barras, sin espacios.
   - Ejemplo: si la URL es `https://dev.azure.com/qa-corp` → `AZURE_DEVOPS_ORG=qa-corp`.
4. ¿No tienes organización? Crea una **gratis** desde https://dev.azure.com → **New organization**.

### 2. `AZURE_DEVOPS_PROJECT` (el proyecto)

1. Dentro de tu organización, en el panel izquierdo aparece la lista de proyectos.
2. Abre el proyecto donde están tus **Historias de Usuario**.
3. El **nombre del proyecto** está arriba a la izquierda, al lado del logo. Cópialo **exacto** (respeta mayúsculas, espacios y acentos).
   - Ejemplo: `Proyecto QA` → `AZURE_DEVOPS_PROJECT=Proyecto QA`.
4. Para saber el **ID de una HU**: abre la historia y mira la URL, termina en `/_workitems/edit/12345` → el **12345** es el ID.

### 3. `AZURE_DEVOPS_PAT` (el Personal Access Token)

1. Entra a la página de tokens: **https://dev.azure.com/<tu-org>/_usersSettings/tokens**
   - Alternativa: clic en tu **avatar** (arriba a la derecha) → **Personal Access Tokens**.
2. Clic en **+ New Token** (botón azul).
3. **Name**: `qa-testcase-generator` (o el que prefieras).
4. **Organization**: tu organización (o "All accessible organizations").
5. **Scopes**: clic en **Show all scopes** → busca **Work Items** → marca **Read & Write**.
   - ⚠️ Mínimo imprescindible: `Work Items → Read & Write`.
   - Si luego quieres Test Plans, agrega también `Test Management → Read & Write`.
6. **Expiration**: 30 o 90 días (al vencer hay que crear otro y actualizar el `.env`).
7. Clic en **Create**.
8. ⚠️ **COPIA EL TOKEN EN ESE MOMENTO**: solo se muestra **una vez** (en color). Pégalo en `AZURE_DEVOPS_PAT` **sin comillas, sin espacios, sin saltos de línea**.
9. Guarda el archivo.

### Ejemplo de `.env` ya llenado

```
AZURE_DEVOPS_ORG=qa-corp
AZURE_DEVOPS_PROJECT=Proyecto QA
AZURE_DEVOPS_PAT=xr6abcdefghijklmnopqrstuvwxyz1234567890
OLLAMA_MODEL=qwen2.5:7b-instruct
```

---

### Paso 2. Levantar

```powershell
docker compose up -d --build
```

La primera vez descarga el modelo de Ollama (~4.7 GB). Si el modelo no está, ejecuta:

```powershell
docker exec -it qa-testcase-ollama ollama pull qwen2.5:7b-instruct
```

### Paso 3. Verificar la conexión con Azure (NO te saltes este paso)

1. Abre **http://localhost:8000** y pulsa **Ctrl+F5** (refresco limpio).
2. El **banner amarillo "MODO DEMO" debe haber desaparecido**. Si sigue, el `.env` aún tiene valores plantilla → repite el Paso 1.
3. Clic en el botón **"Probar conexión Azure"** → debe decir:
   > "✔ Conexión OK: organización, PAT y proyecto válidos. Permisos de Work Items OK."
4. Escribe el **ID de una HU real** y clic en **"Solo ver la HU"** → verás el título, descripción y criterios de esa historia.

Si algo falla, mira la tabla de abajo.

### Paso 4. Usar

1. Escribe el **ID de la HU** (y opcionalmente varios IDs separados por coma).
2. Elige la **cantidad** de casos y las **instrucciones** (o un preset).
3. **Generar casos de prueba** → el agente lee la HU de Azure y el LLM local genera los casos.
4. **Revisa/edita** cada caso (título, descripción, precondiciones, pasos, criterios que cubre).
5. (Opcional) **Pasar a GPT** → descarga `.md` para que ChatGPT (plan GO) mejore los casos → **Importar mejora de GPT**.
6. **Crear en Azure DevOps** → crea los `Test Case` **enlazados a la HU** (aparecerán en la pestaña "Tested by" de la HU). El resultado muestra enlaces clicables a cada Test Case.

---

## Troubleshooting (si algo falla)

| Síntoma | Causa | Solución |
|---------|-------|----------|
| 400 "Configura AZURE_DEVOPS_*" | `.env` con valores plantilla o vacíos | Llenar `.env` con valores reales (Paso 1) y `docker compose up -d --build` |
| Banner "MODO DEMO" no desaparece | `.env` tiene `tu-organizacion` / `tu_pat_aqui` | Reemplazar por valores reales |
| "Probar conexión" → org no válida / HTTP 404 | `AZURE_DEVOPS_ORG` mal escrita | Verificar la URL real `https://dev.azure.com/<org>`; sin `https://`, sin `/` |
| HTTP 401 al probar | PAT incorrecto, con espacios, o vencido | Crear un PAT nuevo y pegarlo sin espacios (Paso 3) |
| "El proyecto 'X' no aparece en la organización" | `AZURE_DEVOPS_PROJECT` mal escrito, o el PAT no cubre esa org/proyecto | Copiar el nombre exacto; en el PAT seleccionar "All accessible organizations" |
| Sin permisos de Work Items (203/403) | El PAT no tiene `Work Items → Read & Write` | Editar/crear el PAT con ese scope (Paso 3, punto 5) |
| 404 al leer la HU (`/api/hu/{id}`) | El ID no existe o el PAT no ve ese work item | Verificar el ID real en `/_workitems/edit/<ID>` |
| `/api/generate` 502 "No se pudo conectar con Ollama" | El modelo no está descargado | `docker exec -it qa-testcase-ollama ollama pull qwen2.5:7b-instruct` |

---

## Modo demo (sin Azure DevOps)

Si no configuras `AZURE_DEVOPS_*`, el sistema entra en **modo demo**: usa una HU de ejemplo, la generación con Ollama funciona igual, y el botón "Crear" **simula** (no inserta nada). Es ideal para probar antes de tener el PAT.

## Velocidad y barra de progreso

- La generación es lenta a propósito: el modelo corre en **CPU** y genera token a token (~7 tokens/s). 5 casos ≈ 2-5 min.
- El front muestra una **barra de progreso en vivo** (tokens, tokens/s, tiempo) vía streaming SSE.
- Para acelerar: `OLLAMA_MODEL=qwen2.5:3b-instruct` (~2-3x más rápido), pedir menos casos, o esperar la 2ª generación (el modelo queda cargado 30 min).

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | Estado del servicio, modelo y si Azure está configurado |
| GET | `/api/test-azure` | Valida org + PAT + proyecto + permisos de Work Items |
| GET | `/api/hu/{id}` | Obtiene la HU de Azure DevOps |
| GET | `/api/generate-stream` | Genera casos con streaming SSE (progreso en vivo) |
| POST | `/api/generate` | Genera casos (bloqueante) |
| POST | `/api/create` | Crea los test cases en Azure DevOps enlazados a la HU |

## Notas

- El PAT **nunca sale** del contenedor; se lee desde `.env` (que **no** se versiona).
- La conexión usa la REST API `api-version=7.1`.
- Para cambiar de modelo solo edita `OLLAMA_MODEL` en `.env` y `docker compose up -d`.