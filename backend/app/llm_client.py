import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from .azure_client import parse_criteria
from .config import settings

AVG_TOKENS_PER_CASE = 400


class LLMError(Exception):
    pass


class TestCaseGenerationError(Exception):
    pass


def _extract_min_steps(instructions: str) -> Optional[int]:
    if not instructions:
        return None
    patterns = [
        r"por\s+lo\s+menos\s+(\d+)\s+pasos",
        r"al\s+menos\s+(\d+)\s+pasos",
        r"m[ií]nimo\s+(\d+)\s+pasos",
        r"(?:créame|craame|hazme|haz|haga|genérame|genera|dame|crea)\s+(\d+)\s+pasos",
        r"(\d+)\s+pasos\s+a\s+validar",
        r"(\d+)\s+pasos\s+por\s+caso",
        r"\b(\d+)\s+pasos\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, instructions, re.IGNORECASE)
        if match:
            return max(2, min(int(match.group(1)), 20))
    return None


def build_prompt(
    work_item: Dict[str, Any],
    quantity: int,
    instructions: str,
) -> str:
    criteria = work_item.get("criteria_list") or []
    if not criteria:
        criteria = parse_criteria(work_item.get("acceptance_criteria"))
    criteria_block = "\n".join(
        f"{i}. {c}" for i, c in enumerate(criteria, start=1)
    ) or "(sin criterios de aceptación)"

    requested_steps = _extract_min_steps(instructions)
    if requested_steps:
        min_steps = requested_steps
        depth_directive = (
            f"El QA solicitó EXPLÍCITAMENTE al menos {min_steps} pasos por caso. "
            f"NO entregues menos de {min_steps} pasos en cada caso; usa pasos adicionales "
            "para validar caracteres especiales, valores límite, negativos y bordes. "
            "Genera pasos detallados y suficientes para validar a fondo cada escenario."
        )
    elif quantity <= 2:
        min_steps = 5
        depth_directive = (
            f"Como solo se generarán {quantity} casos, CADA caso debe ser EXHAUSTIVO y autosuficiente:\n"
            "  - mínimo 5 pasos, con acciones detalladas y resultados verificables.\n"
            "  - precondiciones completas (datos de entrada, estado, permisos, entorno).\n"
            "  - cubrir el mayor número de criterios de aceptación posible, incluyendo variantes negativas y de límite.\n"
            "  - descripción clara del objetivo y del riesgo que mitiga."
        )
    elif quantity <= 4:
        min_steps = 3
        depth_directive = (
            "Cada caso debe ser detallado y cubrir bien su escenario:\n"
            "  - mínimo 3 pasos, con acciones claras.\n"
            "  - precondiciones concretas (datos, estado, permisos).\n"
            "  - incluir variantes negativas o de límite cuando apliquen."
        )
    else:
        min_steps = 2
        depth_directive = "Casos directos y variados: mínimo 2 pasos cada uno."

    if criteria:
        coverage_directive = (
            f"COBERTURA OBLIGATORIA: los {quantity} casos, en conjunto, deben cubrir TODOS los criterios de aceptación. "
            "Cada caso debe validar la mayor cantidad de criterios posible y reflejarlo en su campo 'criterios'. "
            "Si la cantidad solicitada es pequeña, haz que cada caso abarque varios criterios en sus pasos. "
            "Indica en 'summary' si algún criterio quedó sin cubrir."
        )
    else:
        coverage_directive = ""

    example_block = """{
  "analisis": "Componentes: asignadores por departamento, infraestructura central, sesiones de verificadores, monitoreo. Riesgos: pérdida de independencia entre departamentos, sesiones expiradas por inactividad, regresiones al centralizar, monitoreo incompleto. Ambigüedades: qué se considera 'periodo prolongado', alcance del monitoreo en tiempo real. Edge cases: caída de conectividad, operación concurrente de dos departamentos.",
  "title": "Centralización de los asignadores de todos los departamentos en el Datacenter Nacional",
  "description": "Verificar que los asignadores de mesas digitalizadas de todos los departamentos se encuentren centralizados en el Datacenter Nacional y que no permanezcan instancias operativas locales independientes.",
  "priority": 1,
  "type": "funcional",
  "preconditions": "Existe un inventario oficial de los departamentos que utilizan el asignador. El Datacenter Nacional está disponible. Se dispone de acceso de verificación para cada departamento.",
  "criterios": [1],
  "steps": [
    {"action": "Consultar el inventario oficial de departamentos que deben utilizar el asignador centralizado.", "expected": "Se identifica el conjunto completo de departamentos cubiertos por la solución centralizada."},
    {"action": "Ingresar al entorno del Datacenter Nacional y consultar las instancias de asignadores disponibles.", "expected": "Se identifican instancias centralizadas correspondientes a todos los departamentos del inventario."},
    {"action": "Comparar cada departamento del inventario contra las instancias disponibles en el Datacenter.", "expected": "Cada departamento cuenta con su asignador centralizado y no existen departamentos excluidos."},
    {"action": "Verificar que el acceso operativo de cada departamento se realice contra la infraestructura centralizada.", "expected": "Las conexiones operativas de los departamentos utilizan el asignador del Datacenter Nacional."}
  ]
}"""

    return f"""
Eres un QA senior con enfoque ISTQB / QA Lead, especializado en diseño de casos de prueba profesionales y profundos (nada genérico).

Analiza la siguiente Historia de Usuario y genera exactamente {quantity} casos de prueba.

## HISTORIA DE USUARIO
ID: {work_item.get('id')}
Título: {work_item.get('title')}
Tipo: {work_item.get('type')}

### Descripción
{work_item.get('description') or '(sin descripción)'}

### Criterios de Aceptación
{criteria_block}

### Justificación
{work_item.get('justification') or '(sin justificación)'}

## REQUISITOS EXTRA DEL QA
{instructions or '(ninguno, usa tu criterio)'}

## CALIDAD POR CANTIDAD
{depth_directive}

{coverage_directive}

## EJEMPLO DE CALIDAD (imita EXACTAMENTE este nivel de detalle y profundidad)
{example_block}

## REGLAS DE SALIDA
0. ANTES de generar los casos, analiza la HU y escribe el campo "analisis" con los componentes funcionales, riesgos, ambigüedades y edge cases que detectes.
1. Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin markdown.
2. La estructura debe ser exactamente:
{{
  "analisis": "análisis previo de la HU: componentes, riesgos, ambigüedades y edge cases",
  "summary": "resumen breve del enfoque de pruebas",
  "test_cases": [
    {{
      "title": "título descriptivo SIN prefijos TC-XXX",
      "description": "descripción breve del caso",
      "priority": 1,
      "type": "funcional|regresion|integracion|usabilidad|rendimiento|seguridad",
      "preconditions": "precondiciones o vacío",
      "criterios": [1, 3],
      "steps": [
        {{"action": "paso de acción", "expected": "resultado esperado"}}
      ]
    }}
  ]
}}
3. Cada caso debe tener al menos {min_steps} pasos y cada paso debe tener action y expected.
4. "criterios" es la lista de índices (empezando en 1) de los Criterios de Aceptación que ese caso cubre; puede ser vacía [].
5. El campo "title" NO debe llevar prefijos como "TC-001:" ni numeración; solo un título descriptivo.
6. Los casos deben ser variados: feliz, negativos, límites, edge cases.
7. Las precondiciones deben ser específicas del negocio y verificables, como en el ejemplo.

## INSTRUCCIONES DEL QA — OBLIGATORIAS (última palabra)
Son de máxima prioridad dentro del CONTENIDO de los casos (títulos, pasos, prioridades, tipos, precondiciones, enfoque) y deben cumplirse en TODOS los casos generados:
{instructions or "(ninguna)"}
""".strip()


COMMENT_STATE_TEXT = {
    "done": "La HU pasa a estado DONE (validada / cerrada).",
    "bloqueo": "La HU queda BLOQUEADA.",
    "dependencia": "La HU queda en espera por una DEPENDENCIA.",
}


def build_comment_prompt(
    work_item: Dict[str, Any],
    note: str,
    state: str = "",
    cause: str = "",
) -> str:
    criteria = work_item.get("criteria_list") or []
    criteria_line = (
        f"{len(criteria)} criterios de aceptación"
        if criteria
        else "sin criterios detallados"
    )
    st = (state or "").strip().lower()
    state_line = COMMENT_STATE_TEXT.get(st, "")
    cause = (cause or "").strip()
    motive_parts: List[str] = []
    if state_line:
        motive_parts.append(state_line)
        if st in ("bloqueo", "dependencia") and cause:
            label = (
                "Causa del bloqueo"
                if st == "bloqueo"
                else "Elemento del que se depende"
            )
            motive_parts.append(
                f'{label}: "{cause}". Usa EXACTAMENTE esa información; NO inventes detalles.'
            )
        elif st in ("bloqueo", "dependencia"):
            motive_parts.append(
                "El QA NO indicó la causa/detalle: NO inventes motivos; "
                "menciónalo en términos generales."
            )
    note = (note or "").strip()
    if note:
        motive_parts.append(f"Observaciones adicionales del QA: {note}")
    motive_block = (
        "\n".join(f"- {p}" for p in motive_parts)
        or "- (sin motivo específico: usa tu criterio con profesionalismo)"
    )
    return f"""
Eres un QA senior. Redacta UN comentario breve y profesional para publicar en la Historia de Usuario de Azure DevOps.

## Historia de Usuario
ID: {work_item.get('id')}
Título: {work_item.get('title')}
Estado actual en Azure: {work_item.get('state') or 'N/D'}
Descripción: {(work_item.get('description') or '(sin descripción)')[:900]}
Criterios: {criteria_line}

## Motivo del comentario (estado destino + detalle del QA)
{motive_block}

Requisitos:
- Entre 3 y 6 líneas, tono profesional y natural (que no suene a plantilla).
- Integra de forma natural: (1) el estado destino, (2) la causa o dependencia si se indicó, (3) las observaciones del QA.
- NO saludos, NO firma, NO markdown, NO comillas envolviendo el texto.
- NO uses JSON ni llaves {{}}: responde con TEXTO PLANO.
- Responde SOLO con el texto del comentario.
""".strip()


def _clean_comment(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:text|markdown|json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            lowered = {str(k).strip().lower(): v for k, v in obj.items()}
            for key in ("comentario", "comment", "texto", "text", "respuesta"):
                val = lowered.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            strings = [v for v in obj.values() if isinstance(v, str) and v.strip()]
            if strings:
                return max(strings, key=len).strip()
    return text


def _resolve_provider(provider: Optional[str]) -> str:
    resolved = (provider or "").strip().lower() or settings.default_provider
    if resolved not in ("ollama", "gemini", "kiro"):
        resolved = settings.default_provider
    if resolved not in settings.enabled_providers_list:
        raise LLMError(
            f"El motor '{resolved}' está deshabilitado en este despliegue "
            f"(ENABLED_PROVIDERS en .env habilita: {', '.join(settings.enabled_providers_list) or 'ninguno'}). "
            "Actívalo en .env y reinicia con: docker compose up -d, o elige otro motor."
        )
    if resolved == "gemini" and not settings.gemini_configured:
        raise LLMError(
            "Gemini no está configurado: agrega GEMINI_API_KEY=<tu key> en el archivo .env "
            "(API key de https://aistudio.google.com/apikey) y reinicia con: docker compose up -d"
        )
    if resolved == "kiro" and not settings.kiro_configured:
        raise LLMError(
            "Kiro no está configurado: agrega KIRO_API_KEY=<tu key ksk_...> en el archivo .env "
            "(app.kiro.dev -> API Keys) y reinicia con: docker compose up -d --build"
        )
    return resolved


def generate_comment(
    work_item: Dict[str, Any],
    note: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    state: str = "",
    cause: str = "",
) -> str:
    resolved = _resolve_provider(provider)
    streamer = {
        "gemini": _stream_once_gemini,
        "kiro": _stream_once_kiro,
    }.get(resolved, _stream_once)
    prompt = build_comment_prompt(work_item, note, state, cause)
    kwargs: Dict[str, Any] = {"model_override": model, "max_tokens": 600}
    if streamer is _stream_once:
        kwargs["json_format"] = False
    text: Optional[str] = None
    error: Optional[str] = None
    for event in streamer(prompt, 400, **kwargs):
        if event["type"] == "result":
            text = event.get("text")
            error = event.get("error")
            break
    if error:
        raise LLMError(error)
    cleaned = _clean_comment(text)
    if not cleaned:
        raise LLMError("El modelo no devolvió texto para el comentario.")
    return cleaned


def generate_test_cases(
    work_item: Dict[str, Any],
    quantity: int,
    instructions: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    events = list(stream_test_cases(work_item, quantity, instructions, provider, model))
    done = next((ev["data"] for ev in events if ev["type"] == "done"), None)
    if done is None:
        error = next((ev["data"].get("detail") for ev in events if ev["type"] == "error"), None)
        raise TestCaseGenerationError(error or "No se generaron casos de prueba.")
    return done


def stream_test_cases(
    work_item: Dict[str, Any],
    quantity: int,
    instructions: str,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Iterator[Dict[str, Any]]:
    try:
        resolved = _resolve_provider(provider)
    except LLMError as exc:
        yield {"type": "error", "data": {"detail": str(exc)}}
        return

    max_tokens = (
        settings.gemini_max_tokens
        if resolved in ("gemini", "kiro")
        else settings.ollama_max_tokens
    )
    streamer = {
        "gemini": _stream_once_gemini,
        "kiro": _stream_once_kiro,
    }.get(resolved, _stream_once)

    prompt = build_prompt(work_item, quantity, instructions)
    estimated = min(quantity * AVG_TOKENS_PER_CASE, max_tokens)
    yield {"type": "start", "data": {"estimated_tokens": estimated, "provider": resolved}}

    cases: List[Dict[str, Any]] = []
    summary = ""
    current_prompt = prompt

    for attempt in range(1, 3):
        last_text = None
        error = None
        for event in streamer(current_prompt, estimated, model_override=model):
            if event["type"] == "result":
                last_text = event["text"]
                error = event["error"]
                break
            yield event

        if error:
            yield {"type": "error", "data": {"detail": error}}
            return

        if not last_text:
            yield {"type": "error", "data": {"detail": "El modelo no devolvió texto."}}
            return

        try:
            data = _parse_json(last_text)
        except Exception as exc:
            head = last_text[:300].replace("\n", " ")
            tail = last_text[-300:].replace("\n", " ")
            print(
                f"[llm] parse failed hu={work_item.get('id')} err={exc} "
                f"head={head!r} tail={tail!r}",
                flush=True,
            )
            yield {
                "type": "error",
                "data": {"detail": f"No se pudo interpretar la respuesta del modelo: {exc}"},
            }
            return

        if isinstance(data, list) and data and isinstance(data[0], dict):
            data = {"test_cases": data}

        if isinstance(data, dict):
            if not summary:
                summary = data.get("summary", "")
            raw_cases = data.get("test_cases") or []
            if isinstance(raw_cases, list):
                cases.extend(
                    _normalize_case(c, len(cases) + i + 1)
                    for i, c in enumerate(raw_cases)
                )

        if len(cases) >= quantity:
            break

        missing = quantity - len(cases)
        current_prompt = (
            prompt
            + f"\n\nIMPORTANTE: hasta ahora solo generaste {len(cases)} casos. "
            f"Genera EXACTAMENTE {missing} casos adicionales (numerados TC-{len(cases) + 1:03d} en adelante). "
            "Devuelve únicamente el JSON con esos casos adicionales."
        )
        estimated = min(max(missing, 1) * AVG_TOKENS_PER_CASE, max_tokens)
        yield {
            "type": "progress",
            "data": {
                "tokens": 0,
                "elapsed": 0.0,
                "tokens_per_sec": 0.0,
                "percent": 0,
                "estimated": estimated,
                "note": f"Reintentando: faltan {missing} casos…",
            },
        }

    cases = cases[:quantity]

    if not cases:
        yield {
            "type": "error",
            "data": {"detail": "El modelo no generó casos de prueba."},
        }
        return

    criteria_list = work_item.get("criteria_list") or []
    if criteria_list:
        covered = set()
        for case in cases:
            covered.update(case.get("criterios") or [])
        uncovered = [i for i in range(1, len(criteria_list) + 1) if i not in covered]
        if uncovered:
            summary = (
                summary
                + f"\n⚠ Criterios sin cubrir: {', '.join(str(i) for i in uncovered)}"
            ).strip()

    yield {
        "type": "done",
        "data": {
            "summary": summary,
            "test_cases": cases,
        },
    }


def _classify_ollama_error(status: int, body: str) -> str:
    model = settings.ollama_model
    if status == 404 and "not found" in body.lower():
        return (
            f"El modelo '{model}' NO está instalado en Ollama. "
            f"Instálalo con: docker exec -it qa-testcase-ollama ollama pull {model}  "
            f"(o, si la red corporativa lo bloquea, impórtalo desde un GGUF con "
            f"scripts\\importar_modelo.ps1)."
        )
    if body:
        try:
            err = json.loads(body).get("error")
            if err:
                return f"Ollama respondió HTTP {status}: {err}"
        except json.JSONDecodeError:
            pass
        return f"Ollama respondió HTTP {status}: {body[:200]}"
    return f"Ollama respondió HTTP {status} (sin detalle)."


def _classify_ollama_exception(exc: Exception) -> str:
    base = settings.ollama_url
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        msg = f"Ollama NO está disponible (no se puede conectar a {base}). Verifica que el contenedor 'qa-testcase-ollama' esté levantado."
    elif isinstance(exc, httpx.TimeoutException):
        msg = "Timeout de Ollama. El modelo puede estar cargándose o la generación es muy larga."
    elif isinstance(exc, httpx.SSLError):
        msg = f"Error SSL al conectar con Ollama ({base})."
    else:
        msg = f"Error de red con Ollama ({base})."
    return f"{msg} Detalle: {exc}"


def _stream_once(
    prompt: str,
    estimated: int,
    model_override: Optional[str] = None,
    max_tokens: Optional[int] = None,
    json_format: bool = True,
) -> Iterator[Dict[str, Any]]:
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": True,
        "keep_alive": "30m",
        "options": {
            "temperature": settings.ollama_temperature,
            "num_predict": max_tokens or settings.ollama_max_tokens,
            "num_ctx": settings.ollama_num_ctx,
        },
    }
    if json_format:
        payload["format"] = "json"

    buf = ""
    token_count = 0
    start = time.time()
    last_yield = 0.0

    try:
        with httpx.stream(
            "POST",
            f"{settings.ollama_url}/api/generate",
            json=payload,
            timeout=600.0,
        ) as resp:
            if resp.status_code != 200:
                body = ""
                try:
                    body = resp.read().decode("utf-8", "replace")
                except Exception:
                    pass
                yield {
                    "type": "result",
                    "text": None,
                    "error": _classify_ollama_error(resp.status_code, body),
                }
                return

            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                token = chunk.get("response", "")
                buf += token
                token_count += 1

                if chunk.get("done"):
                    break

                now = time.time()
                if now - last_yield >= 0.25:
                    last_yield = now
                    elapsed = now - start
                    tps = round(token_count / elapsed, 1) if elapsed > 0 else 0.0
                    percent = min(int(token_count / estimated * 100), 99)
                    yield {
                        "type": "progress",
                        "data": {
                            "tokens": token_count,
                            "elapsed": round(elapsed, 1),
                            "tokens_per_sec": tps,
                            "percent": percent,
                            "estimated": estimated,
                        },
                    }
    except httpx.HTTPError as exc:
        yield {
            "type": "result",
            "text": None,
            "error": _classify_ollama_exception(exc),
        }
        return

    yield {"type": "result", "text": buf, "error": None}


def _classify_gemini_error(status: int, body: str, model: str = "") -> str:
    model = model or settings.gemini_model
    msg = ""
    if body:
        try:
            msg = (json.loads(body).get("error") or {}).get("message") or ""
        except json.JSONDecodeError:
            msg = body[:200]
    lowered = msg.lower()
    if status in (400, 403) and ("api key" in lowered or "api_key" in lowered or "permission" in lowered):
        return (
            f"Gemini rechazó la API key (HTTP {status}): {msg[:200]} "
            f"Revisa GEMINI_API_KEY en .env (https://aistudio.google.com/apikey)."
        )
    if status == 404:
        return (
            f"El modelo '{model}' no existe o no está disponible para tu cuenta (HTTP 404): "
            f"{msg[:200]} Revisa GEMINI_MODEL en .env."
        )
    if status == 429:
        return (
            f"Gemini alcanzó su límite de cuota (HTTP 429): {msg[:200]} "
            f"Espera unos minutos o revisa tu plan en AI Studio."
        )
    if msg:
        return f"Gemini respondió HTTP {status}: {msg[:200]}"
    return f"Gemini respondió HTTP {status}: {(body[:200] or 'sin detalle').strip()}"


def _classify_gemini_exception(exc: Exception) -> str:
    base = settings.gemini_url
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        msg = f"No se puede conectar con Gemini ({base}). Verifica la red o el proxy corporativo."
    elif isinstance(exc, httpx.TimeoutException):
        msg = "Timeout con Gemini. La generación es muy larga o la API está lenta."
    elif isinstance(exc, httpx.SSLError):
        msg = f"Error SSL al conectar con Gemini ({base}). Podría ser inspección TLS (Netskope)."
    else:
        msg = f"Error de red con Gemini ({base})."
    return f"{msg} Detalle: {exc}"


GEMINI_RETRY_STATUSES = (429, 500, 502, 503, 504)


def _gemini_model_chain() -> List[str]:
    chain = [settings.gemini_model]
    for extra in (settings.gemini_fallback_models or "").split(","):
        name = extra.strip()
        if name and name not in chain:
            chain.append(name)
    return chain


def _stream_once_gemini(
    prompt: str,
    estimated: int,
    model_override: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    headers = {
        "x-goog-api-key": settings.gemini_api_key,
        "Content-Type": "application/json",
    }
    plan: List[Any] = []
    for mi, model in enumerate(_gemini_model_chain()):
        for attempt in ((1, 2) if mi == 0 else (1,)):
            plan.append((model, attempt))

    last_error = "Gemini no respondió."

    for idx, (model, attempt) in enumerate(plan):
        if idx > 0:
            note = (
                f"Gemini sin respuesta, reintento 2/2 con {model}…"
                if attempt > 1
                else f"Pruebo modelo alternativo: {model}…"
            )
            yield {
                "type": "progress",
                "data": {
                    "tokens": 0,
                    "elapsed": 0.0,
                    "tokens_per_sec": 0.0,
                    "percent": 0,
                    "estimated": estimated,
                    "note": note,
                },
            }
            time.sleep(3)

        url = (
            f"{settings.gemini_url.rstrip('/')}/v1beta/models/{model}"
            f":streamGenerateContent?alt=sse"
        )
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": settings.gemini_temperature,
                "maxOutputTokens": max_tokens or settings.gemini_max_tokens,
                "responseMimeType": "application/json",
            },
        }

        buf = ""
        token_count = 0
        start = time.time()
        last_yield = 0.0

        try:
            with httpx.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(600.0, connect=15.0),
            ) as resp:
                if resp.status_code != 200:
                    body = ""
                    try:
                        body = resp.read().decode("utf-8", "replace")
                    except Exception:
                        pass
                    last_error = _classify_gemini_error(resp.status_code, body, model)
                    if (
                        resp.status_code not in GEMINI_RETRY_STATUSES
                        and resp.status_code != 404
                    ):
                        yield {"type": "result", "text": None, "error": last_error}
                        return
                else:
                    for line in resp.iter_lines():
                        line = (line or "").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue

                        candidates = chunk.get("candidates") or []
                        parts = (
                            (candidates[0].get("content") or {}).get("parts") or []
                            if candidates
                            else []
                        )
                        token = "".join(
                            str(p.get("text") or "")
                            for p in parts
                            if not p.get("thought")
                        )
                        if token:
                            buf += token
                            token_count = max(token_count, len(buf) // 4)

                        usage = chunk.get("usageMetadata") or {}
                        if usage.get("candidatesTokenCount"):
                            token_count = max(
                                token_count, int(usage["candidatesTokenCount"])
                            )

                        finished = any(c.get("finishReason") for c in candidates)
                        if finished:
                            break

                        now = time.time()
                        if now - last_yield >= 0.25:
                            last_yield = now
                            elapsed = now - start
                            tps = round(token_count / elapsed, 1) if elapsed > 0 else 0.0
                            percent = min(int(token_count / estimated * 100), 99)
                            yield {
                                "type": "progress",
                                "data": {
                                    "tokens": token_count,
                                    "elapsed": round(elapsed, 1),
                                    "tokens_per_sec": tps,
                                    "percent": percent,
                                    "estimated": estimated,
                                },
                            }

                    if buf.strip():
                        yield {"type": "result", "text": buf, "error": None}
                        return
                    last_error = "Gemini devolvió una respuesta vacía."
        except httpx.HTTPError as exc:
            last_error = _classify_gemini_exception(exc)

    yield {"type": "result", "text": None, "error": last_error}


def _kiro_binary() -> Optional[str]:
    found = shutil.which("kiro-cli")
    if found:
        return found
    fallback = "/root/.local/bin/kiro-cli"
    return fallback if os.path.isfile(fallback) else None


def _kiro_extract_text(line: str) -> str:
    line = line.strip()
    if not line or not line.startswith("{"):
        return ""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return ""
    found: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and value and key in ("text", "content"):
                    found.append(value)
                elif isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return "".join(found)


def _classify_kiro_error(
    returncode: int, detail: str, timed_out: bool, timeout: int,
    model: Optional[str] = None,
) -> str:
    detail = (detail or "").strip()
    if timed_out:
        return (
            f"Kiro superó el tiempo límite ({timeout}s) y se canceló. "
            "Prueba con menos casos o revisa tu plan en app.kiro.dev."
        )
    if detail:
        lowered = detail.lower()
        if "api key" in lowered or "unauthorized" in lowered or "401" in lowered:
            return (
                f"Kiro rechazó la API key (exit {returncode}): {detail[:300]} "
                "Revisa KIRO_API_KEY en .env (app.kiro.dev -> API Keys)."
            )
        if "no such file" in lowered or "not found" in lowered:
            return (
                "kiro-cli no está instalado en la imagen del backend. "
                "Reconstruye con: docker compose up -d --build"
            )
        return f"Kiro CLI falló (exit {returncode}): {detail[:300]}"
    if model:
        return (
            f"Kiro CLI rechazó el modelo '{model}' (exit {returncode}, sin mensaje). "
            "Prueba con 'Auto (recomendado)' u otro modelo del selector; "
            "si persiste, verifica KIRO_API_KEY y tu plan en app.kiro.dev."
        )
    return (
        f"Kiro CLI terminó con código {returncode} sin mensaje. "
        "Verifica KIRO_API_KEY y tu suscripción Kiro Pro en app.kiro.dev."
    )


def _stream_once_kiro(
    prompt: str,
    estimated: int,
    model_override: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    binary = _kiro_binary()
    if not binary:
        yield {
            "type": "result",
            "text": None,
            "error": (
                "kiro-cli no está instalado en la imagen del backend. "
                "Reconstruye con: docker compose up -d --build"
            ),
        }
        return

    args = [
        binary,
        "chat",
        "--no-interactive",
        "--output-format",
        "stream-json",
        "--trust-tools=",
    ]
    engine = (settings.kiro_engine or "").strip().lower()
    if engine in ("v1", "v2", "v3"):
        args += ["--agent-engine", engine]
    model = (model_override or settings.kiro_model or "").strip()
    if model:
        args += ["--model", model]

    env = dict(os.environ)
    env["KIRO_API_KEY"] = settings.kiro_api_key
    env["PATH"] = f"{env.get('PATH', '')}:/root/.local/bin"

    tmpdir = tempfile.mkdtemp(prefix="kiro-run-")
    proc: Optional[subprocess.Popen] = None
    watchdog: Optional[threading.Timer] = None
    timed_out = {"flag": False}
    buf = ""
    token_count = 0
    start = time.time()
    last_yield = 0.0

    def _kill_on_timeout() -> None:
        timed_out["flag"] = True
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=tmpdir,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        watchdog = threading.Timer(settings.kiro_timeout, _kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()

        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(prompt)
        proc.stdin.close()

        raw_lines: List[str] = []
        for line in proc.stdout:
            raw_lines.append(line)
            delta = _kiro_extract_text(line)
            if delta:
                buf += delta
                token_count = max(token_count, len(buf) // 4)
                now = time.time()
                if now - last_yield >= 0.25:
                    last_yield = now
                    elapsed = now - start
                    tps = round(token_count / elapsed, 1) if elapsed > 0 else 0.0
                    percent = min(int(token_count / estimated * 100), 99)
                    yield {
                        "type": "progress",
                        "data": {
                            "tokens": token_count,
                            "elapsed": round(elapsed, 1),
                            "tokens_per_sec": tps,
                            "percent": percent,
                            "estimated": estimated,
                        },
                    }

        proc.wait()

        if proc.returncode != 0:
            noise = "".join(ln for ln in raw_lines if not ln.strip().startswith("{"))
            yield {
                "type": "result",
                "text": None,
                "error": _classify_kiro_error(
                    proc.returncode or -1,
                    noise,
                    timed_out["flag"],
                    settings.kiro_timeout,
                    model or None,
                ),
            }
            return

        if not buf.strip():
            yield {
                "type": "result",
                "text": None,
                "error": (
                    "Kiro respondió vacío (sin texto útil en stream-json). "
                    "Revisa KIRO_MODEL/KIRO_ENGINE en .env."
                ),
            }
            return
    except OSError as exc:
        yield {
            "type": "result",
            "text": None,
            "error": f"No se pudo ejecutar kiro-cli: {exc}",
        }
        return
    finally:
        if watchdog is not None:
            watchdog.cancel()
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
        shutil.rmtree(tmpdir, ignore_errors=True)

    yield {"type": "result", "text": buf, "error": None}


def _parse_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        last_error: Exception = exc
    decoder = json.JSONDecoder()
    fallback_any: Any = None
    fallback_list: Any = None
    for match in re.finditer(r"[\[{]", text):
        try:
            value, _end = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(value, dict) and "test_cases" in value:
            return value
        if fallback_any is None:
            fallback_any = value
        if (
            fallback_list is None
            and isinstance(value, list)
            and value
            and isinstance(value[0], dict)
        ):
            fallback_list = value
    if fallback_list is not None:
        return fallback_list
    if fallback_any is not None:
        return fallback_any
    raise ValueError(f"JSON no encontrado en la respuesta ({last_error})")


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_case(raw: Any, index: int) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {"title": f"TC-{index:03d}"}
    steps = raw.get("steps") or []
    normalized_steps: List[Dict[str, str]] = []
    for step in steps:
        if isinstance(step, dict):
            normalized_steps.append(
                {
                    "action": str(step.get("action") or "").strip(),
                    "expected": str(step.get("expected") or "").strip(),
                }
            )
    criterios: List[int] = []
    for raw_c in raw.get("criterios") or []:
        try:
            criterios.append(int(raw_c))
        except (TypeError, ValueError):
            pass
    title = str(raw.get("title") or "").strip()
    title = re.sub(r"^\s*TC-\d+\s*[:.\-–]?\s*", "", title, flags=re.IGNORECASE).strip()
    if not title:
        title = f"Caso de prueba {index:03d}"
    return {
        "title": title,
        "description": str(raw.get("description") or ""),
        "priority": _to_int(raw.get("priority"), 2),
        "type": str(raw.get("type") or "funcional"),
        "preconditions": str(raw.get("preconditions") or ""),
        "criterios": criterios,
        "steps": normalized_steps,
    }


def steps_to_tcm_html(steps: List[Dict[str, str]]) -> str:
    parts = [f'<steps id="0" last="{len(steps) * 2}">']
    for i, step in enumerate(steps, start=1):
        action = _escape_html(step.get("action", ""))
        expected = _escape_html(step.get("expected", ""))
        parts.append(
            f'<step id="{i * 2}" type="ValidateStep">'
            f'<parameterizedString isformatted="true">&lt;DIV&gt;&lt;P&gt;{action}&lt;/P&gt;&lt;/DIV&gt;</parameterizedString>'
            f'<parameterizedString isformatted="true">{expected}</parameterizedString>'
            f'<description/></step>'
        )
    parts.append("</steps>")
    return "".join(parts)


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )