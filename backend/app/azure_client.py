import base64
import re
from html.parser import HTMLParser
from typing import Any, Dict, List

import httpx

from .config import settings

_BLOCK_TAGS = {"p", "div", "br", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("li", "p", "tr"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return html
    lines = [line.strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def parse_criteria(text: str) -> List[str]:
    if not text:
        return []
    criteria: List[str] = []
    current = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^\s*(?:[-*•]|\d+[.)])", line):
            if current:
                criteria.append(current.strip())
            current = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
        elif current:
            current += " " + line
        else:
            current = line
    if current:
        criteria.append(current.strip())
    skip = {"criterio de aceptación", "criterios de aceptación", "criterio de aceptacion", "criterios de aceptacion"}
    return [c for c in criteria if c and c.lower() not in skip]


class AzureDevOpsError(Exception):
    pass


def sample_work_item(work_item_id: int) -> Dict[str, Any]:
    acceptance_criteria = (
        "1. El usuario puede iniciar sesión con credenciales válidas.\n"
        "2. Se muestra un mensaje de error claro si las credenciales son inválidas.\n"
        "3. La cuenta se bloquea tras 5 intentos fallidos consecutivos.\n"
        "4. Hay un enlace para recuperar la contraseña olvidada."
    )
    return {
        "id": work_item_id,
        "type": "User Story",
        "title": "[DEMO] Inicio de sesión de usuario",
        "description": (
            "Como usuario registrado, quiero iniciar sesión con mi correo y contraseña "
            "para acceder a mi cuenta de forma segura."
        ),
        "acceptance_criteria": acceptance_criteria,
        "criteria_list": parse_criteria(acceptance_criteria),
        "justification": "Garantizar que ningún formulario digitalizado se pierda por fallas del OCR/ICR.",
        "state": "New",
        "created_by": "Modo DEMO (sin Azure DevOps)",
    }


class AzureDevOpsClient:
    def __init__(self) -> None:
        self._base = settings.api_base
        self._project = settings.azure_devops_project
        token = f":{settings.azure_devops_pat}".encode()
        self._auth = {
            "Authorization": "Basic " + base64.b64encode(token).decode()
        }

    def _url(self, path: str) -> str:
        return f"{self._base}/{self._project}/_apis{path}"

    def _get(self, path: str, params: Dict[str, Any]) -> httpx.Response:
        resp = httpx.get(
            self._url(path),
            params=params,
            headers=self._auth,
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise AzureDevOpsError(
                f"Azure DevOps GET {path} -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp

    def get_work_item(self, work_item_id: int) -> Dict[str, Any]:
        resp = self._get(
            f"/wit/workitems/{work_item_id}",
            {
                "api-version": "7.1",
                "$expand": "Relations",
            },
        )
        data = resp.json()
        fields = data.get("fields", {})
        description = html_to_text(fields.get("System.Description"))
        acceptance_criteria = html_to_text(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria"))
        justification = html_to_text(
            fields.get("Microsoft.VSTS.CMMI.Justification")
            or fields.get("Microsoft.VSTS.Common.BusinessValue")
        )
        return {
            "id": data.get("id"),
            "type": fields.get("System.WorkItemType"),
            "title": fields.get("System.Title"),
            "description": description,
            "acceptance_criteria": acceptance_criteria,
            "criteria_list": parse_criteria(acceptance_criteria),
            "justification": justification,
            "state": fields.get("System.State"),
            "created_by": fields.get("System.CreatedBy", {}).get("displayName"),
        }

    def get_work_item_url(self, work_item_id: int) -> str:
        return f"{settings.api_base}/{self._project}/_apis/wit/workItems/{work_item_id}"

    def _test_headers(self) -> Dict[str, str]:
        return {**self._auth, "Content-Type": "application/json"}

    def get_or_create_test_plan(self, plan_name: str) -> Dict[str, Any]:
        resp = httpx.get(
            self._url("/test/plans"),
            params={"api-version": "7.1"},
            headers=self._auth,
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise AzureDevOpsError(f"Test Plans GET -> HTTP {resp.status_code}: {resp.text[:300]}")
        plans = resp.json().get("value", [])
        if settings.azure_devops_test_plan_id:
            for p in plans:
                if str(p.get("id")) == settings.azure_devops_test_plan_id:
                    return p
        for p in plans:
            if p.get("name") == plan_name:
                return p
        if plans:
            return plans[0]
        body = {
            "name": plan_name,
            "area": {"name": self._project},
            "iteration": self._project,
        }
        resp = httpx.post(
            self._url("/test/plans"),
            params={"api-version": "7.1"},
            headers=self._test_headers(),
            json=body,
            timeout=30.0,
        )
        if resp.status_code not in (200, 201):
            raise AzureDevOpsError(
                f"Test Plan create -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def get_or_create_suite(self, plan_id: int, suite_name: str) -> Dict[str, Any]:
        resp = httpx.get(
            self._url(f"/test/plans/{plan_id}/suites"),
            params={"api-version": "7.1"},
            headers=self._auth,
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise AzureDevOpsError(
                f"Test Suites GET -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        suites = resp.json().get("value", [])
        for s in suites:
            if s.get("name") == suite_name:
                return s
        body = {"suiteType": "StaticTestSuite", "name": suite_name}
        resp = httpx.post(
            self._url(f"/test/plans/{plan_id}/suites"),
            params={"api-version": "7.1"},
            headers=self._test_headers(),
            json=body,
            timeout=30.0,
        )
        if resp.status_code not in (200, 201):
            raise AzureDevOpsError(
                f"Test Suite create -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def add_test_case_to_suite(self, plan_id: int, suite_id: int, test_case_id: int) -> None:
        resp = httpx.post(
            self._url(f"/test/plans/{plan_id}/suites/{suite_id}/testcases/{test_case_id}"),
            params={"api-version": "7.1"},
            headers=self._test_headers(),
            timeout=30.0,
        )
        if resp.status_code not in (200, 201):
            raise AzureDevOpsError(
                f"Add Test Case a suite -> HTTP {resp.status_code}: {resp.text[:300]}"
            )

    def test_connection(self) -> Dict[str, Any]:
        report = {
            "org_ok": False,
            "pat_ok": False,
            "project_found": False,
            "wit_access_ok": False,
        }
        try:
            resp = httpx.get(
                f"{settings.api_base}/_apis/projects",
                params={"api-version": "7.1"},
                headers=self._auth,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "report": report, "error": f"No se pudo conectar con Azure: {exc}"}

        if resp.status_code != 200:
            return {
                "ok": False,
                "report": report,
                "error": f"GET /_apis/projects -> HTTP {resp.status_code}: {resp.text[:200]}",
            }

        report["org_ok"] = True
        report["pat_ok"] = True
        projects = [p.get("name") for p in resp.json().get("value", [])]
        if self._project not in projects:
            return {
                "ok": False,
                "report": report,
                "error": f"El proyecto '{self._project}' no aparece en la organización '{settings.azure_devops_org}'. Proyectos visibles: {projects[:10]}",
            }

        report["project_found"] = True
        try:
            resp2 = httpx.get(
                self._url("/wit/workitemtypes"),
                params={"api-version": "7.1"},
                headers=self._auth,
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "report": report, "error": f"Error al validar Work Items: {exc}"}

        if resp2.status_code == 200:
            report["wit_access_ok"] = True
            return {
                "ok": True,
                "report": report,
                "error": None,
                "message": "Conexión OK: organización, PAT y proyecto válidos. Permisos de Work Items OK.",
            }

        return {
            "ok": False,
            "report": report,
            "error": (
                f"El PAT no tiene permisos de Work Items (HTTP {resp2.status_code}). "
                "Revisa que el token tenga el scope 'Work Items → Read & Write'."
            ),
        }

    def create_test_case(
        self,
        title: str,
        description: str,
        steps_html: str,
        user_story_id: int,
        priority: int = 2,
        preconditions: str = "",
    ) -> Dict[str, Any]:
        fields: Dict[str, Any] = {
            "/fields/System.Title": title,
        }
        if description:
            fields["/fields/System.Description"] = description
        if priority:
            fields["/fields/Microsoft.VSTS.Common.Priority"] = priority
        if preconditions:
            fields["/fields/Custom.Preconditions"] = preconditions
        if steps_html:
            fields["/fields/Microsoft.VSTS.TCM.Steps"] = steps_html

        patch = [{"op": "add", "path": path, "value": value} for path, value in fields.items()]
        patch.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Related",
                    "url": self.get_work_item_url(user_story_id),
                },
            }
        )

        resp = httpx.post(
            self._url(f"/wit/workitems/$Test Case"),
            params={"api-version": "7.1"},
            headers={**self._auth, "Content-Type": "application/json-patch+json"},
            json=patch,
            timeout=30.0,
        )
        if resp.status_code not in (200, 201):
            raise AzureDevOpsError(
                f"Azure DevOps create Test Case -> HTTP {resp.status_code}: {resp.text[:500]}"
            )

        data = resp.json()
        return {
            "id": data.get("id"),
            "url": data.get("url"),
            "title": data.get("fields", {}).get("System.Title"),
        }


azure_client = AzureDevOpsClient()