"""Pruebas del orquestador multiagente (lógica pura, sin LLM)."""
from app.agents import (
    _plan_agents,
    _split_quantity,
    _risk_relevant,
    _consolidate,
    _valid_case,
)


def _hu(**kw):
    base = {"title": "", "description": "", "acceptance_criteria": "", "criteria_list": []}
    base.update(kw)
    return base


def test_plan_sin_riesgo():
    agents = _plan_agents(_hu(title="Reporte de ventas mensual"))
    assert agents == ["positivos", "negativos"]


def test_plan_con_riesgo_auto():
    agents = _plan_agents(_hu(title="Login con contraseña y token"))
    assert "riesgo" in agents


def test_risk_relevant_detecta_seguridad():
    assert _risk_relevant(_hu(description="manejo de permisos y autorización"))
    assert not _risk_relevant(_hu(description="listar productos del catálogo"))


def test_split_quantity_suma_exacta():
    agents = ["positivos", "negativos", "riesgo"]
    alloc = _split_quantity(agents, 10)
    assert sum(alloc.values()) == 10
    assert all(v >= 1 for v in alloc.values())


def test_split_quantity_dos_agentes():
    alloc = _split_quantity(["positivos", "negativos"], 5)
    assert sum(alloc.values()) == 5


def test_valid_case_rechaza_sin_pasos():
    assert not _valid_case({"title": "X", "steps": []})


def test_valid_case_rechaza_paso_generico():
    assert not _valid_case(
        {"title": "X", "steps": [{"action": "verificar que funcione", "expected": "ok"}]}
    )


def test_valid_case_acepta_paso_real():
    assert _valid_case(
        {"title": "X", "steps": [{"action": "ingresar usuario admin", "expected": "accede al panel"}]}
    )


def test_consolidate_dedup_por_titulo():
    g = [
        {"title": "Login válido", "steps": [{"action": "a", "expected": "b"}]},
        {"title": "login  válido", "steps": [{"action": "a", "expected": "b"}, {"action": "c", "expected": "d"}]},
        {"title": "Login inválido", "steps": [{"action": "a", "expected": "b"}]},
    ]
    out = _consolidate(g, 10)
    titulos = [c["title"] for c in out]
    assert len(out) == 2  # los dos "login válido" colapsan
    # conserva el de más pasos
    valido = next(c for c in out if c["title"].lower().startswith("login  válido") or len(c["steps"]) == 2)
    assert len(valido["steps"]) == 2


def test_consolidate_respeta_cantidad():
    g = [
        {"title": f"Caso {i}", "steps": [{"action": "a", "expected": "b"}]}
        for i in range(5)
    ]
    assert len(_consolidate(g, 3)) == 3
