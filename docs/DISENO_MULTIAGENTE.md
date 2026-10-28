# Diseño: generación multiagente de casos de prueba

> **Estado: IMPLEMENTADO (fase 1 + fase 2).** Concurrencia por hilos, Kiro limitado
> a 1 agente, corte por inactividad en los 3 motores, y barras por agente en el
> front. Se activa con `AGENTS_ENABLED=true` (default). Ver sección 11.

Este documento describe cómo pasar de **una llamada / un prompt** a **varios agentes en paralelo** que se consolidan, y cómo evitar que el sistema "se quede pensando" sin fin. No reescribe el proyecto: reusa los streamers que ya existen.

---

## 1. Cómo está hoy (línea base)

Un solo prompt pide todo y lo resuelve un solo modelo.

```
Front (streamOne, 1 HU a la vez)
  -> GET /api/generate-stream
    -> stream_test_cases()          backend/app/llm_client.py
      -> build_prompt()             1 prompt gigante (análisis+positivos+negativos+cobertura)
      -> streamer único             _stream_once | _stream_once_gemini | _stream_once_kiro
      -> hasta 2 intentos           si faltan casos, reenvía el prompt completo
    -> _parse_json -> _normalize_case
```

| Parte | Trabajo que hace | Archivo |
|---|---|---|
| `build_prompt` | Mete todo en un prompt | `backend/app/llm_client.py` |
| `stream_test_cases` | Llama 1 streamer, reintenta 2 veces | `backend/app/llm_client.py` |
| `_stream_once_*` | Habla con Ollama / Gemini / Kiro | `backend/app/llm_client.py` |
| `generate_stream` | Pasa eventos SSE al front | `backend/app/main.py` |
| `generate` (front) | Procesa HU en serie (`for await`) | `backend/static/app.js` |

No existe: cola, planificador, concurrencia, ni reparto de tareas.

---

## 2. Qué causa "se queda pensando" (por motor)

El problema no es un solo timeout. Son tres puntos distintos.

1. **Kiro CLI es un subproceso de hasta 600 s.** `kiro_timeout=600` en `backend/app/config.py`. El watchdog solo mata por tiempo total; no corta por "sin texto nuevo". Si el modelo divaga, esperas 10 minutos.
2. **Ollama con `num_ctx=4096` y prompt enorme.** El prompt grande (ejemplo largo + reglas) hace que el 7B relea todo y vaya lento. `timeout=600.0` fijo en `_stream_once`.
3. **El reintento duplica el trabajo.** Si faltan casos, `current_prompt = prompt + nota`: reenvía el prompt completo otra vez. Dobla el costo y el tiempo.

Lo que **no** hay hoy:

- Corte por inactividad (si no llegan tokens en N segundos).
- Límite de reintentos configurable (está fijo en 2).
- Cancelación controlada salvo que el front cierre el SSE a mano.
- Registro del motivo por el que una tarea no terminó.

---

## 3. Idea del diseño

Cada "agente" es **una llamada a un `_stream_once_*` con un prompt distinto**. Ya tenemos los streamers. Lo nuevo es:

- un **orquestador** que lanza varios agentes a la vez cuando son independientes,
- un **consolidador** que corre al final (depende de los demás),
- **límites por agente** (timeout, inactividad, reintentos) en vez de uno global.

### Agentes (solo los que tienen sentido para este proyecto)

| # | Agente | Qué produce | Depende de |
|---|---|---|---|
| 1 | Positivos | Camino feliz, cubre criterios de aceptación | nada |
| 2 | Negativos y límites | Validaciones, bordes, datos inválidos | nada |
| 3 | Riesgo / seguridad | Solo si la HU lo amerita | nada |
| 4 | Consolidador | Junta todo, quita duplicados, revisa cobertura | 1, 2 y 3 |

- **En paralelo seguro:** 1, 2 y 3 (son independientes).
- **En serie:** 4 espera a que terminen los demás.

Esto respeta la regla de **no paralelizar dependencias**.

El agente 3 no siempre corre: el reparto decide incluirlo según la HU (p. ej. si menciona permisos, datos sensibles, pagos). Así no se crean agentes de más.

### Flujo nuevo

```
stream_test_cases_multi()
  |
  |-- reparto: ¿incluir agente 3? (según la HU)
  |
  |== en paralelo (asyncio.gather) =========
  |   agente 1 positivos   -> casos[]
  |   agente 2 negativos   -> casos[]
  |   agente 3 riesgo       -> casos[]   (opcional)
  |=========================================
  |
  |-- cada agente: su propio timeout + corte por inactividad + reintentos
  |-- si un agente falla o se cuelga: los demás SIGUEN, se guarda su parcial
  |
  |-- consolidador (agente 4): dedup + cobertura + recorte a quantity
  |
  -> done: { test_cases[], summary, agents[] }
```

---

## 4. Concurrencia real (importante)

El código de hoy es **síncrono bloqueante** (`httpx.stream`, `for line in resp.iter_lines()`, `subprocess` + hilo). Para correr 3 agentes a la vez hay dos caminos:

**Opción A — hilos (menos cambios).** Correr cada `_stream_once_*` en un `ThreadPoolExecutor`. No se tocan los streamers. El orquestador junta resultados con `concurrent.futures`. Simple, pero el streaming de progreso de varios agentes a la vez se vuelve más difícil de intercalar en un solo SSE.

**Opción B — async (más limpio a futuro).** Pasar los streamers a `httpx.AsyncClient` y `asyncio.create_subprocess_exec` para Kiro. Permite `asyncio.gather`, cancelación nativa (`task.cancel()`) y una cola async para intercalar eventos. Más trabajo inicial.

**Recomendación:** empezar con **A (hilos)** porque no rompe los streamers actuales ni el resto del flujo, y dejar B como evolución si el intercalado de progreso lo pide. El reparto de tareas cabe en ambas.

> Decisión abierta para ti: A rápido, o B limpio desde el inicio. (Ver sección 9.)

---

## 5. Evitar el bloqueo infinito

Un **supervisor por agente**, no un timeout global.

| Control | Qué hace | Hoy |
|---|---|---|
| Timeout por operación | Corta un agente a los N s | 600 s fijo |
| Corte por inactividad | Si no llegan tokens en N s, cancela ESE agente | no existe |
| Máx. reintentos | Tope configurable por agente | fijo en 2 |
| Aislamiento de fallo | Un agente cae, los demás siguen | no (es 1 solo) |
| Resultado parcial | Se guarda lo que alcanzó a producir cada agente | no |
| Motivo de corte | Se registra por qué no terminó | no |

El corte por inactividad va **dentro del loop** de cada streamer: ya se mide `last_yield` / `start`; basta comparar contra `now - last_token > inactivity_timeout` y romper el loop marcando el motivo.

Para Kiro, el watchdog por tiempo total ya existe; se **añade** un segundo watchdog que mira si el `buf` creció en los últimos N s.

---

## 6. Settings nuevos (en `config.py`)

```
# Multiagente
AGENTS_ENABLED=true                 # activar/desactivar el modo multiagente
AGENTS_PARALLEL=3                   # máx. agentes simultáneos
AGENT_INCLUDE_RISK=auto             # auto | always | never (agente 3)

# Supervisión por agente
AGENT_OP_TIMEOUT=180                # s por agente (reemplaza el 600 global por operación)
AGENT_INACTIVITY_TIMEOUT=45         # s sin tokens nuevos -> cancelar ese agente
AGENT_MAX_RETRIES=1                 # reintentos por agente (hoy es 2 fijo)

# Kiro: control de gasto
KIRO_AGENTS_PARALLEL=1              # cuántos agentes Kiro a la vez (créditos)
```

`KIRO_TIMEOUT` sigue existiendo como tope duro del subproceso; `AGENT_OP_TIMEOUT` corta antes si aplica.

---

## 7. Formato de eventos SSE (para el front)

Hoy el front espera un solo stream. El modo multiagente necesita decir **de qué agente** viene cada evento. Se agrega el campo `agent`.

```
event: agent_start   data: {"agent": "positivos", "label": "Positivos"}
event: progress      data: {"agent": "positivos", "tokens": 120, "percent": 40, ...}
event: agent_done    data: {"agent": "positivos", "count": 3}
event: agent_error   data: {"agent": "riesgo", "reason": "inactividad 45s"}
event: progress      data: {"agent": "consolidador", ...}
event: done          data: {"test_cases": [...], "summary": "...", "agents": [
                              {"name":"positivos","status":"ok","count":3},
                              {"name":"negativos","status":"ok","count":4},
                              {"name":"riesgo","status":"timeout","count":0}
                            ]}
```

**Compatibilidad:** los eventos `progress` / `done` / `error` mantienen su forma; `agent` es opcional. El front viejo que no lo lea sigue funcionando (muestra una sola barra). El front nuevo puede pintar **una barra por agente**.

---

## 8. Cambios por archivo (resumen, sin código todavía)

| Archivo | Cambio |
|---|---|
| `backend/app/config.py` | Settings de la sección 6 |
| `backend/app/agents.py` (**nuevo**) | Orquestador, definición de agentes, prompts especializados, supervisor por agente, consolidador |
| `backend/app/llm_client.py` | Extraer prompt specialized + corte por inactividad en los 3 `_stream_once_*`; `stream_test_cases` delega en `agents.py` si `AGENTS_ENABLED` |
| `backend/app/main.py` | `generate_stream` reenvía el campo `agent`; `/api/health` expone `agents_enabled` |
| `backend/static/app.js` | (opcional fase 2) pintar una barra por agente; leer `agents[]` del `done` |
| `docs/ARQUITECTURA.md` | Documentar el modo multiagente |
| `AGENTS.md` | Nota del nuevo módulo y settings |

Prompts especializados: cada agente recibe la MISMA HU pero con un encargo distinto al final (su "rol"), reusando `build_prompt` con un parámetro `role`.

---

## 9. Decisiones que necesito de ti

1. **Concurrencia:** hilos (rápido, sin tocar streamers) o async (limpio, más trabajo). → recomiendo hilos primero.
2. **Kiro y créditos:** ¿paralelizar Kiro igual que los otros, o `KIRO_AGENTS_PARALLEL=1` para que gaste poco? → recomiendo limitarlo.
3. **Front:** ¿fase 1 solo backend (una barra, pero multiagente por dentro) o incluir ya las barras por agente?

---

## 10. Orden de implementación sugerido

1. Settings nuevos + `agents.py` con el orquestador en hilos y los 4 roles.
2. Corte por inactividad en los 3 streamers.
3. `stream_test_cases` delega en `agents.py` detrás de `AGENTS_ENABLED`.
4. SSE con campo `agent`; `/api/health` con `agents_enabled`.
5. (Fase 2) barras por agente en el front.
6. Documentar en `ARQUITECTURA.md` y `AGENTS.md`.

Cada paso es probable en Docker con `python -m py_compile backend\app\*.py` y `docker compose up -d --build`.


## 11. Lo que se implementó

Fase 1 (backend, hilos) y fase 2 (barras por agente) ya están en el código.

| Archivo | Cambio aplicado |
|---|---|
| `backend/app/config.py` | Settings: `agents_enabled`, `agents_parallel`, `agent_include_risk`, `kiro_agents_parallel`, `agent_op_timeout`, `agent_inactivity_timeout`, `agent_max_retries` |
| `backend/app/agents.py` (nuevo) | Orquestador con `ThreadPoolExecutor`, roles, reparto de cantidad, supervisión (timeout + inactividad + reintentos), consolidación con dedup por título e intercalado por rol |
| `backend/app/llm_client.py` | `build_prompt(role=...)`; parámetro `inactivity_timeout` + corte por inactividad en los 3 streamers (Kiro con 2º watchdog); `stream_test_cases` delega en `agents.py` si `AGENTS_ENABLED` |
| `backend/app/main.py` | `/api/health` expone `agents_enabled`; `generate_stream` reenvía los nuevos eventos SSE |
| `backend/static/*` | Barras por agente en el loader; CSS con variables del tema; cache `v=42` |
| `.env.example` | Sección 8 con los settings nuevos |

Verificado en `python:3.12-slim`: `py_compile` OK, import sin ciclos OK, plan de agentes y reparto correctos. Falta la prueba contra un motor real (`docker compose up -d --build` y generar una HU).

### Cómo apagarlo
`AGENTS_ENABLED=false` en `.env` + `docker compose up -d` → vuelve al modo de un solo prompt.
