import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterator, List, Optional

from .config import settings

AVG_TOKENS_PER_CASE = 400

# Roles de agente. "parallel" define si corre en la primera fase (independiente)
# o en la fase final (consolidador, depende de los demás).
AGENT_ROLES = {
    "positivos": {
        "label": "Positivos",
        "parallel": True,
        "role": (
            "Genera ÚNICAMENTE casos de camino feliz y flujos principales. "
            "Prioriza cubrir los criterios de aceptación con datos válidos y el "
            "comportamiento esperado del sistema. NO generes casos negativos ni de límite."
        ),
    },
    "negativos": {
        "label": "Negativos y límites",
        "parallel": True,
        "role": (
            "Genera ÚNICAMENTE casos negativos, de validación y de valores límite: "
            "datos inválidos, campos vacíos, formatos incorrectos, bordes (mínimos, "
            "máximos, cero), y mensajes de error esperados. NO repitas el camino feliz."
        ),
    },
    "riesgo": {
        "label": "Riesgo y seguridad",
        "parallel": True,
        "role": (
            "Genera ÚNICAMENTE casos de riesgo y seguridad cuando la HU lo amerite: "
            "autenticación, autorización, permisos, datos sensibles, inyección, "
            "concurrencia y fallos de infraestructura. Si la HU no tiene superficie de "
            "riesgo, devuelve test_cases vacío."
        ),
    },
}

# Pistas que activan el agente de riesgo en modo auto.
_RISK_HINTS = (
    "login", "sesión", "sesion", "contraseña", "password", "token", "pago", "pagos",
    "permiso", "permisos", "rol", "roles", "autoriz", "autentic", "seguridad",
    "sensible", "privado", "cifrad", "encript", "dato personal", "datos personales",
    "api key", "credencial", "acceso",
)


def _risk_relevant(work_item: Dict[str, Any]) -> bool:
    blob = " ".join(
        str(work_item.get(k) or "")
        for k in ("title", "description", "acceptance_criteria", "justification")
    ).lower()
    blob += " " + " ".join(str(c).lower() for c in (work_item.get("criteria_list") or []))
    return any(h in blob for h in _RISK_HINTS)


def _plan_agents(work_item: Dict[str, Any]) -> List[str]:
    agents = ["positivos", "negativos"]
    mode = settings.agent_include_risk_mode
    if mode == "always":
        agents.append("riesgo")
    elif mode == "auto" and _risk_relevant(work_item):
        agents.append("riesgo")
    return agents


def _split_quantity(agents: List[str], quantity: int) -> Dict[str, int]:
    # Reparto base equitativo; el resto va a positivos y negativos.
    n = len(agents)
    base = max(1, quantity // n)
    alloc = {a: base for a in agents}
    assigned = base * n
    i = 0
    weighted = [a for a in agents if a in ("positivos", "negativos")] or agents
    while assigned < quantity:
        alloc[weighted[i % len(weighted)]] += 1
        assigned += 1
        i += 1
    return alloc


def _run_one_agent(
    name: str,
    work_item: Dict[str, Any],
    quantity: int,
    instructions: str,
    model: Optional[str],
    streamer,
    max_tokens: int,
    out: "queue.Queue",
) -> None:
    # Importación local para evitar ciclo de import con llm_client.
    from .llm_client import build_prompt, _parse_json, _normalize_case

    cfg = AGENT_ROLES[name]
    label = cfg["label"]
    estimated = min(quantity * AVG_TOKENS_PER_CASE, max_tokens)
    out.put({"type": "agent_start", "data": {"agent": name, "label": label}})

    role_text = cfg["role"] + (
        f"\nGenera aproximadamente {quantity} casos para tu enfoque."
        if quantity
        else ""
    )
    prompt = build_prompt(work_item, quantity, instructions, role=role_text)

    retries = max(0, settings.agent_max_retries)
    inactivity = max(0, settings.agent_inactivity_timeout)
    deadline = time.time() + settings.agent_op_timeout if settings.agent_op_timeout else None

    cases: List[Dict[str, Any]] = []
    reason = ""
    for attempt in range(retries + 1):
        if deadline and time.time() > deadline:
            reason = f"timeout {settings.agent_op_timeout}s"
            break
        last_text: Optional[str] = None
        error: Optional[str] = None
        try:
            for event in streamer(
                prompt, estimated, model_override=model,
                inactivity_timeout=inactivity,
            ):
                if event["type"] == "result":
                    last_text = event.get("text")
                    error = event.get("error")
                    break
                data = dict(event.get("data") or {})
                data["agent"] = name
                out.put({"type": "progress", "data": data})
        except Exception as exc:  # noqa: BLE001 - aislamiento de fallo por agente
            error = f"excepción: {exc}"

        if error and not last_text:
            reason = error
            continue
        if not last_text:
            reason = "sin texto"
            continue
        try:
            parsed = _parse_json(last_text)
        except Exception as exc:  # noqa: BLE001
            reason = f"parseo: {exc}"
            continue
        if isinstance(parsed, list):
            parsed = {"test_cases": parsed}
        raw_cases = (parsed or {}).get("test_cases") or [] if isinstance(parsed, dict) else []
        if isinstance(raw_cases, list) and raw_cases:
            cases = [_normalize_case(c, i + 1) for i, c in enumerate(raw_cases)]
            reason = ""
            break
        reason = "sin casos"

    status = "ok" if cases else ("timeout" if reason.startswith("timeout") else "error")
    if not cases:
        print(
            f"[agents] hu={work_item.get('id')} agente={name} status={status} "
            f"motivo={reason or 'sin casos'}",
            flush=True,
        )
    out.put({
        "type": "agent_done" if cases else "agent_error",
        "data": {
            "agent": name, "label": label,
            "count": len(cases), "status": status,
            "reason": reason,
        },
    })
    out.put({"__cases__": name, "cases": cases, "status": status, "reason": reason})


def _norm_title(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


_GENERIC_STEP = re.compile(
    r"^(verificar que funcione|probar|validar|funciona correctamente|ok|n/?a)\.?$",
    re.IGNORECASE,
)


def _valid_case(case: Dict[str, Any]) -> bool:
    """Un caso es útil si tiene título y al menos un paso con acción y esperado reales."""
    if not _norm_title(case.get("title")):
        return False
    steps = case.get("steps") or []
    good = [
        s for s in steps
        if str(s.get("action") or "").strip()
        and str(s.get("expected") or "").strip()
        and not _GENERIC_STEP.match(str(s.get("action") or "").strip())
    ]
    return len(good) >= 1


def _consolidate(
    grouped: List[Dict[str, Any]],
    quantity: int,
) -> List[Dict[str, Any]]:
    # Dedup por título normalizado; ante choque conserva el de más pasos.
    best: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for case in grouped:
        if not _valid_case(case):
            continue
        key = _norm_title(case.get("title"))
        if key not in best:
            best[key] = case
            order.append(key)
        else:
            if len(case.get("steps") or []) > len(best[key].get("steps") or []):
                best[key] = case
    merged = [best[k] for k in order]
    return merged[:quantity] if quantity else merged


def stream_test_cases_multi(
    work_item: Dict[str, Any],
    quantity: int,
    instructions: str,
    resolved_provider: str,
    model: Optional[str],
) -> Iterator[Dict[str, Any]]:
    from .llm_client import (
        _stream_once, _stream_once_gemini, _stream_once_kiro,
    )

    streamer = {
        "gemini": _stream_once_gemini,
        "kiro": _stream_once_kiro,
    }.get(resolved_provider, _stream_once)
    max_tokens = (
        settings.gemini_max_tokens
        if resolved_provider in ("gemini", "kiro")
        else settings.ollama_max_tokens
    )

    agents = _plan_agents(work_item)
    alloc = _split_quantity(agents, quantity)

    yield {
        "type": "start",
        "data": {
            "estimated_tokens": min(quantity * AVG_TOKENS_PER_CASE, max_tokens),
            "provider": resolved_provider,
            "agents": [{"name": a, "label": AGENT_ROLES[a]["label"]} for a in agents],
            "multiagent": True,
        },
    }

    # Límite de concurrencia: Kiro se limita aparte para controlar créditos.
    if resolved_provider == "kiro":
        max_workers = max(1, settings.kiro_agents_parallel)
    else:
        max_workers = max(1, settings.agents_parallel)

    out: "queue.Queue" = queue.Queue()
    results: Dict[str, Dict[str, Any]] = {}

    def _worker() -> None:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(
                    _run_one_agent, name, work_item, alloc[name],
                    instructions, model, streamer, max_tokens, out,
                )
                for name in agents
            ]
            for f in futures:
                f.result()
        out.put(None)  # centinela de fin

    driver = threading.Thread(target=_worker, daemon=True)
    driver.start()

    while True:
        item = out.get()
        if item is None:
            break
        if "__cases__" in item:
            results[item["__cases__"]] = item
            continue
        yield item

    driver.join(timeout=5)

    # Consolidación (agente final, en serie, depende de los demás).
    yield {"type": "agent_start", "data": {"agent": "consolidador", "label": "Consolidador"}}
    ordered: List[Dict[str, Any]] = []
    # Intercalar por rol da variedad: toma de a uno de cada agente por ronda.
    buckets = [results.get(a, {}).get("cases", []) for a in agents]
    idx = 0
    while any(idx < len(b) for b in buckets):
        for b in buckets:
            if idx < len(b):
                ordered.append(b[idx])
        idx += 1

    final_cases = _consolidate(ordered, quantity)

    summary_parts = []
    for a in agents:
        r = results.get(a, {})
        summary_parts.append(f"{AGENT_ROLES[a]['label']}: {len(r.get('cases', []))}")
    summary = "Multiagente — " + ", ".join(summary_parts) + f" → {len(final_cases)} tras dedup."

    criteria_list = work_item.get("criteria_list") or []
    if criteria_list:
        covered = set()
        for case in final_cases:
            covered.update(case.get("criterios") or [])
        uncovered = [i for i in range(1, len(criteria_list) + 1) if i not in covered]
        if uncovered:
            summary += f"\n⚠ Criterios sin cubrir: {', '.join(str(i) for i in uncovered)}"

    agents_report = [
        {
            "name": a,
            "label": AGENT_ROLES[a]["label"],
            "status": results.get(a, {}).get("status", "error"),
            "count": len(results.get(a, {}).get("cases", [])),
            "reason": results.get(a, {}).get("reason", ""),
        }
        for a in agents
    ]

    yield {
        "type": "agent_done",
        "data": {"agent": "consolidador", "label": "Consolidador", "count": len(final_cases), "status": "ok"},
    }

    if not final_cases:
        yield {
            "type": "error",
            "data": {
                "detail": "Ningún agente generó casos. " + "; ".join(
                    f"{r['label']}: {r['reason'] or 'sin casos'}" for r in agents_report
                ),
                "agents": agents_report,
            },
        }
        return

    yield {
        "type": "done",
        "data": {
            "summary": summary,
            "test_cases": final_cases,
            "agents": agents_report,
        },
    }
