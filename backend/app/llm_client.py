import json
import re
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from .config import settings

AVG_TOKENS_PER_CASE = 400


class LLMError(Exception):
    pass


class TestCaseGenerationError(Exception):
    pass


def build_prompt(
    work_item: Dict[str, Any],
    quantity: int,
    instructions: str,
) -> str:
    return f"""
Eres un QA senior especializado en diseño de casos de prueba.

Analiza la siguiente Historia de Usuario y genera exactamente {quantity} casos de prueba.

## HISTORIA DE USUARIO
ID: {work_item.get('id')}
Título: {work_item.get('title')}
Tipo: {work_item.get('type')}

### Descripción
{work_item.get('description') or '(sin descripción)'}

### Criterios de Aceptación
{work_item.get('acceptance_criteria') or '(sin criterios de aceptación)'}

## REQUISITOS EXTRA DEL QA
{instructions or '(ninguno, usa tu criterio)'}

## REGLAS DE SALIDA
1. Responde ÚNICAMENTE con un JSON válido, sin texto adicional, sin markdown.
2. La estructura debe ser exactamente:
{{
  "summary": "resumen breve del enfoque de pruebas",
  "test_cases": [
    {{
      "title": "TC-001: título descriptivo",
      "description": "descripción breve del caso",
      "priority": 1,
      "type": "funcional|regresion|integracion|usabilidad|rendimiento|seguridad",
      "preconditions": "precondiciones o vacío",
      "steps": [
        {{"action": "paso de acción", "expected": "resultado esperado"}}
      ]
    }}
  ]
}}
3. Cada caso debe tener al menos 2 pasos y cada paso debe tener action y expected.
4. Los casos deben ser variados: feliz, negativos, límites, edge cases.
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

    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": True,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": settings.ollama_temperature,
            "num_predict": settings.ollama_max_tokens,
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
                    "type": "error",
                    "data": {"detail": f"Ollama respondió HTTP {resp.status_code}"},
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
            "type": "error",
            "data": {"detail": f"No se pudo conectar con Ollama ({settings.ollama_url}): {exc}"},
        }
        return

    try:
        data = _parse_json(buf)
    except Exception as exc:
        yield {
            "type": "error",
            "data": {"detail": f"No se pudo interpretar la respuesta del modelo: {exc}"},
        }
        return

    if not isinstance(data, dict):
        yield {
            "type": "error",
            "data": {"detail": "La respuesta del modelo no es un objeto JSON."},
        }
        return

    cases = data.get("test_cases") or []
    if not isinstance(cases, list) or len(cases) == 0:
        yield {
            "type": "error",
            "data": {"detail": "El modelo no generó casos de prueba."},
        }
        return

    yield {
        "type": "done",
        "data": {
            "summary": data.get("summary", ""),
            "test_cases": [_normalize_case(c, i) for i, c in enumerate(cases, start=1)],
        },
    }


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
    return {
        "title": str(raw.get("title") or f"TC-{index:03d}"),
        "description": str(raw.get("description") or ""),
        "priority": int(raw.get("priority") or 2),
        "type": str(raw.get("type") or "funcional"),
        "preconditions": str(raw.get("preconditions") or ""),
        "steps": normalized_steps,
    }


def steps_to_tcm_html(steps: List[Dict[str, str]]) -> str:
    parts = [f'<steps id="0" last="{len(steps) * 2}">']
    for i, step in enumerate(steps, start=1):
        action = _escape_html(step.get("action", ""))
        expected = _escape_html(step.get("expected", ""))
        parts.append(
            f'<step id="{i * 2 - 1}" type="Action"><parameterizedString>{action}</parameterizedString><description/></step>'
        )
        parts.append(
            f'<step id="{i * 2}" type="ExpectedResult"><parameterizedString>{expected}</parameterizedString><description/></step>'
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