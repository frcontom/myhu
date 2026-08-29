import json
import re
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
""".strip()


def generate_test_cases(
    work_item: Dict[str, Any],
    quantity: int,
    instructions: str,
) -> Dict[str, Any]:
    events = list(stream_test_cases(work_item, quantity, instructions))
    done = next((ev["data"] for ev in events if ev["type"] == "done"), None)
    if done is None:
        error = next((ev["data"].get("detail") for ev in events if ev["type"] == "error"), None)
        raise TestCaseGenerationError(error or "No se generaron casos de prueba.")
    return done


def stream_test_cases(
    work_item: Dict[str, Any],
    quantity: int,
    instructions: str,
) -> Iterator[Dict[str, Any]]:
    prompt = build_prompt(work_item, quantity, instructions)
    estimated = min(quantity * AVG_TOKENS_PER_CASE, settings.ollama_max_tokens)
    yield {"type": "start", "data": {"estimated_tokens": estimated}}

    cases: List[Dict[str, Any]] = []
    summary = ""
    current_prompt = prompt

    for attempt in range(1, 3):
        last_text = None
        error = None
        for event in _stream_once(current_prompt, estimated):
            if event["type"] == "result":
                last_text = event["text"]
                error = event["error"]
                break
            yield event

        if error:
            yield {"type": "error", "data": {"detail": error}}
            return

        try:
            data = _parse_json(last_text)
        except Exception as exc:
            yield {
                "type": "error",
                "data": {"detail": f"No se pudo interpretar la respuesta del modelo: {exc}"},
            }
            return

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
        estimated = min(max(missing, 1) * AVG_TOKENS_PER_CASE, settings.ollama_max_tokens)
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


def _stream_once(
    prompt: str,
    estimated: int,
) -> Iterator[Dict[str, Any]]:
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": True,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": settings.ollama_temperature,
            "num_predict": settings.ollama_max_tokens,
            "num_ctx": 8192,
        },
    }

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
                yield {
                    "type": "result",
                    "text": None,
                    "error": f"Ollama respondió HTTP {resp.status_code}",
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
            "error": f"No se pudo conectar con Ollama ({settings.ollama_url}): {exc}",
        }
        return

    yield {"type": "result", "text": buf, "error": None}


def _parse_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("JSON no encontrado en la respuesta")


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