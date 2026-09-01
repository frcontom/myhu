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
# AZURE_DEVOPS_URL=https://qa-corp.visualstudio.com   ← solo si tu org es *.visualstudio.com
OLLAMA_MODEL=qwen2.5:7b-instruct
```

> **Dominio legacy `*.visualstudio.com`:** si tu URL es `https://tuorg.visualstudio.com/proyecto` (en vez de `dev.azure.com/tuorg`), agrega `AZURE_DEVOPS_URL=https://tuorg.visualstudio.com`. Si no, déjala vacía.

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

**Dos formas de generar los casos de prueba:**

**A. Con el modelo local (Ollama):**
1. Escribe el **ID de la HU** (puedes poner varios separados por coma).
2. Elige la **cantidad** de casos (1-7) y las instrucciones (o un preset).
3. **Generar casos de prueba** → el LLM local los genera con barra de progreso (botón **Cancelar generación** disponible).
4. **Revisa/edita** cada caso: título, precondiciones, descripción, criterios que cubre, pasos (reordénalos con **drag & drop** ⠿).
5. **Crear en Azure DevOps** → crea los `Test Case` enlazados a la HU (pestaña **"Tested by"**, con precondiciones y pasos editables). El panel de **cobertura** (✔/✖) muestra qué criterios quedan sin cubrir y el botón **"Completar cobertura"** genera los faltantes.

**B. Directo con ChatGPT (sin Ollama):**
1. Escribe el **ID de la HU**.
2. **"Pasar a ChatGPT (sin Ollama)"** → se abre un modal: elige la **cantidad** de casos y edita el prompt si quieres.
3. **"Descargar y copiar"** el `.md` (HU + SOLICITUD + JSON de ejemplo).
4. Pégalo en **ChatGPT** → te devuelve el archivo mejorado.
5. **"Importar mejora de GPT"** → se cargan los casos en el editor.
6. **"Crear en Azure DevOps"**.

> El editor **se guarda solo en el navegador** (localStorage): recargar no pierde el trabajo. "Limpiar" borra lo guardado.

---

## CA corporativa / SSL (red con Netskope o proxy)

Si en la red corporativa `docker compose build` falla con `SSLCertVerificationError: self-signed certificate in certificate chain` al ejecutar `pip install`, es porque el proxy de inspección HTTPS (Netskope) firma los certificados de PyPI y el contenedor no confía en la **CA raíz corporativa**.

**Solución (en la máquina afectada):**

1. Coloca los **dos certificados** en `backend/ca/` (PEM/CRT):
   - `netskope-root.crt` (CA raíz: `CN=*.dfw3.goskope.com, O=Netskope Inc.`)
   - `netskope-intermediate.crt` (CA intermedia: `CN=ca.thomasgreg.goskope.com, O=INVOTECSA`)
   - Obténlos desde el store de Windows (`certmgr.msc`) o con `scripts\generar_ca.bat`, y conviértelos:
     ```
     openssl x509 -inform DER -in netskope-root.cer -out netskope-root.crt
     openssl x509 -inform DER -in netskope-intermediate.cer -out netskope-intermediate.crt
     ```

2. Construye **ambas** imágenes (backend + ollama) y levanta:
   ```cmd
   docker compose build --no-cache
   docker compose up -d
   ```

El `Dockerfile` (backend) y el `Dockerfile.ollama` (nuevo) instalan `ca-certificates`, copian `netskope-root.crt` + `netskope-intermediate.crt` a `/usr/local/share/ca-certificates/`, ejecutan `update-ca-certificates`, y configuran `PIP_CERT` (backend) y `SSL_CERT_FILE` (ollama). Si los certificados no existen, el build funciona normal.

> ⚠️ Las CA corporativas se ignoran en git (`backend/ca/*.crt`): **nunca las versiones**.

---

## Si la red corporativa bloquea la descarga del modelo (Cloudflare R2)

Si `ollama pull` falla por política corporativa (bloqueo de descarga de blobs en `*.r2.cloudflarestorage.com`), **importa el modelo offline desde un GGUF** (legítimo, sin evadir la política):

1. **Descarga el GGUF en una red permitida** (HuggingFace):
   - `qwen2.5:7b-instruct` → `Qwen/Qwen2.5-7B-Instruct-GGUF` → `qwen2.5-7b-instruct-q4_k_m.gguf`
   - `deepseek-r1:7b` → `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF`

2. **Impórtalo con el script:**
   ```cmd
   powershell -ExecutionPolicy Bypass -File scripts\importar_modelo.ps1 `
       -GgufPath "C:\models\qwen2.5-7b-instruct-q4_k_m.gguf" `
       -ModelName "qwen2.5:7b-instruct"
   ```

3. El modelo queda en el **volumen persistente** `ollama_data` (no se pierde al reiniciar el contenedor).

4. Reinicia el backend: `docker compose up -d --build`

### Diagnóstico claro de Ollama

El backend ahora distingue estos estados y muestra el mensaje correcto:

| Mensaje del front | Significado | Solución |
|-------------------|-------------|----------|
| "El modelo 'X' NO está instalado en Ollama..." | Ollama arriba, modelo ausente | `ollama pull X` o importar GGUF (script) |
| "Ollama NO está disponible..." | Contenedor `ollama` apagado | `docker compose up -d` |
| "Timeout de Ollama..." | Modelo cargándose / generación muy larga | Esperar; reducir cantidad de casos |
| "Error SSL al conectar con Ollama..." | Certificado Netskope no instalado en Ollama | Instalar CA corporativa en el contenedor ollama |
| "Ollama respondió HTTP {n}: {error}" | Error del endpoint de Ollama | Revisar el error devuelto |

El endpoint `GET /api/health` incluye ahora `ollama: {available, models, model_installed}` para diagnosticar de un vistazo.

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
| `/api/generate` 502 "No se pudo conectar con Ollama" | El modelo no está descargado | `docker exec -it qa-testcase-ollama ollama pull qwen2.5:7b-instruct` o importar GGUF |
| "Ollama respondió HTTP 404" | Modelo no instalado en Ollama | `ollama pull qwen2.5:7b-instruct` o `scripts\importar_modelo.ps1` |
| "Ollama NO está disponible" | Contenedor ollama apagado | `docker compose up -d` |
| "Timeout de Ollama" | Modelo cargándose o generación muy larga | Esperar / reducir cantidad de casos |

---

## Modo demo (sin Azure DevOps)

Si no configuras `AZURE_DEVOPS_*`, el sistema entra en **modo demo**: usa una HU de ejemplo, la generación con Ollama funciona igual, y el botón "Crear" **simula** (no inserta nada). Es ideal para probar antes de tener el PAT.

## Velocidad y barra de progreso

- La generación es lenta a propósito: el modelo corre en **CPU** y genera token a token (~7 tokens/s). 5 casos ≈ 2-5 min.
- El front muestra una **barra de progreso en vivo** (tokens, tokens/s, tiempo) vía streaming SSE, con botón **Cancelar generación**.
- Para acelerar: `OLLAMA_MODEL=qwen2.5:3b-instruct` (~2-3x más rápido), pedir menos casos, o esperar la 2ª generación (el modelo queda cargado 30 min).

## Mejorar la calidad: modelos alternativos

Si quieres un modelo que **razone más** y dé mejores resultados (a costa de velocidad), puedes usar:

| Modelo | Tamaño | Ventaja | Contra |
|--------|--------|---------|--------|
| `qwen2.5:7b-instruct` | ~4.7 GB | Balance calidad/velocidad (actual) | — |
| `deepseek-r1:7b` | ~4.7 GB | **Razona paso a paso** (chain-of-thought): análisis más profundo y casos mejor pensados | ~2x más lento |
| `qwen2.5-coder:7b` | ~4.7 GB | Excelente con JSON estructurado | Menos "pensamiento" |
| `qwen2.5:3b-instruct` | ~2 GB | ~2-3x más rápido | Menos calidad |

**Cómo cambiarlo (ej. a `deepseek-r1:7b`):**
```powershell
# 1. Edita .env → OLLAMA_MODEL=deepseek-r1:7b
# 2. Descarga el modelo
docker exec -it qa-testcase-ollama ollama pull deepseek-r1:7b
# 3. Reinicia
docker compose up -d
```

> ⚠️ El modelo configurado en `.env` debe estar descargado en Ollama (`docker exec -it qa-testcase-ollama ollama list`). Con ~7 GB de RAM libre, `deepseek-r1:7b` es el tope recomendado.

## Comandos útiles

```powershell
# Copiar configuración
Copy-Item .env.example .env

# Levantar (o reiniciar tras cambios de código/.env)
docker compose up -d --build

# Bajar y subir todo (limpieza total)
docker compose down
docker compose up -d --build

# Descargar el modelo si falta
docker exec -it qa-testcase-ollama ollama pull qwen2.5:7b-instruct

# Ver logs del backend
docker logs qa-testcase-backend --tail 50

# Generar la CA corporativa (red con Netskope/proxy)
scripts\generar_ca.bat

# Validar estado y conexión (desde PowerShell)
Invoke-RestMethod http://localhost:8000/api/health
Invoke-RestMethod http://localhost:8000/api/test-azure
```

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
- Los Test Case se crean con: título limpio (sin prefijos TC), descripción, prioridad, precondiciones (`Custom.Preconditions`), pasos (`ValidateStep`, editables) y **enlace "Tested by"** a la HU. La iteración/área se copian de la HU.
- **Publicación opcional a Test Plans**: solo si configuras `AZURE_DEVOPS_TEST_PLAN_ID` en el `.env` (requiere PAT con `Test Management → Read & Write`).