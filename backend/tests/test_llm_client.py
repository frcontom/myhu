"""Pruebas de las piezas puras (sin red, sin LLM, sin Azure)."""
from app.llm_client import (
    _parse_json,
    _normalize_case,
    steps_to_tcm_html,
    _extract_min_steps,
    _clean_comment,
)


def test_parse_json_limpio():
    data = _parse_json('{"test_cases": [{"title": "A"}]}')
    assert data["test_cases"][0]["title"] == "A"


def test_parse_json_con_markdown():
    text = "```json\n{\"test_cases\": [{\"title\": \"B\"}]}\n```"
    data = _parse_json(text)
    assert data["test_cases"][0]["title"] == "B"


def test_parse_json_embebido_en_texto():
    text = 'Aquí tienes: {"test_cases": [{"title": "C"}]} y nada más.'
    data = _parse_json(text)
    assert data["test_cases"][0]["title"] == "C"


def test_parse_json_lista_suelta():
    text = '[{"title": "D", "steps": []}]'
    data = _parse_json(text)
    assert isinstance(data, list)
    assert data[0]["title"] == "D"


def test_parse_json_invalido_lanza():
    try:
        _parse_json("esto no es json")
        assert False, "debió lanzar"
    except ValueError:
        pass


def test_normalize_quita_prefijo_tc():
    case = _normalize_case({"title": "TC-001: Login válido", "priority": "1"}, 1)
    assert case["title"] == "Login válido"
    assert case["priority"] == 1


def test_normalize_prioridad_invalida_default_2():
    case = _normalize_case({"title": "X", "priority": "alta"}, 1)
    assert case["priority"] == 2


def test_normalize_sin_titulo_pone_fallback():
    case = _normalize_case({"steps": []}, 7)
    assert "007" in case["title"]


def test_normalize_steps_limpia_dicts():
    case = _normalize_case(
        {"title": "X", "steps": [{"action": " a ", "expected": " b "}, "basura"]}, 1
    )
    assert case["steps"] == [{"action": "a", "expected": "b"}]


def test_tcm_html_formato_validatestep():
    html = steps_to_tcm_html([{"action": "clic", "expected": "ok"}])
    # El formato que la org reconoce: ValidateStep + 2 parameterizedString.
    assert 'type="ValidateStep"' in html
    assert html.count("parameterizedString") == 4  # 2 aperturas + 2 cierres
    assert 'last="2"' in html


def test_tcm_html_escapa_caracteres():
    html = steps_to_tcm_html([{"action": "a<b>&", "expected": '"x"'}])
    assert "&lt;b&gt;" in html
    assert "&amp;" in html
    assert "&quot;" in html


def test_extract_min_steps():
    assert _extract_min_steps("genera 7 pasos por caso") == 7
    assert _extract_min_steps("al menos 3 pasos") == 3
    assert _extract_min_steps("sin número") is None


def test_clean_comment_quita_json_y_comillas():
    assert _clean_comment('"hola"') == "hola"
    assert _clean_comment('{"comentario": "texto"}') == "texto"
    assert _clean_comment("```text\nplano\n```") == "plano"
