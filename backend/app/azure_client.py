import base64
import re
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

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
        "iteration_path": "",
        "area_path": "",
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
            "iteration_path": fields.get("System.IterationPath"),
            "area_path": fields.get("System.AreaPath"),
        }

    def get_work_item_url(self, work_item_id: int) -> str:
        return f"{settings.api_base}/{self._project}/_apis/wit/workItems/{work_item_id}"

    def list_test_cases_for_hu(self, hu_id: int) -> List[Dict[str, Any]]:
        resp = self._get(
            f"/wit/workitems/{hu_id}",
            {"api-version": "7.1", "$expand": "Relations"},
        )
        ids: List[str] = []
        for rel in resp.json().get("relations") or []:
            if "test" not in (rel.get("rel") or "").lower():
                continue
            match = re.search(r"/workitems/(\d+)$", rel.get("url") or "", re.IGNORECASE)
            if match and match.group(1) != str(hu_id) and match.group(1) not in ids:
                ids.append(match.group(1))
        if not ids:
            return []
        batch = httpx.get(
            self._url("/wit/workitems"),
            params={
                "ids": ",".join(ids),
                "fields": "System.Title,Microsoft.VSTS.Common.Priority",
                "api-version": "7.1",
            },
            headers=self._auth,
            timeout=30.0,
        )
        if batch.status_code != 200:
            raise AzureDevOpsError(
                f"Azure DevOps GET test cases de HU {hu_id} -> HTTP {batch.status_code}: "
                f"{batch.text[:300]}"
            )
        return [
            {
                "id": item.get("id"),
                "title": item.get("fields", {}).get("System.Title", ""),
                "priority": item.get("fields", {}).get("Microsoft.VSTS.Common.Priority"),
            }
            for item in batch.json().get("value", [])
        ]

    def update_test_case(
        self,
        test_case_id: int,
        title: str,
        description: str,
        steps_html: str,
        priority: int = 2,
        preconditions: str = "",
    ) -> Dict[str, Any]:
        fields: Dict[str, Any] = {"/fields/System.Title": title}
        if description:
            fields["/fields/System.Description"] = description
        if priority:
            fields["/fields/Microsoft.VSTS.Common.Priority"] = priority
        if preconditions:
            fields["/fields/Custom.Preconditions"] = preconditions
        if steps_html:
            fields["/fields/Microsoft.VSTS.TCM.Steps"] = steps_html

        patch = [{"op": "add", "path": path, "value": value} for path, value in fields.items()]
        resp = httpx.patch(
            self._url(f"/wit/workitems/{test_case_id}"),
            params={"api-version": "7.1"},
            headers={**self._auth, "Content-Type": "application-patch+json"},
            json=patch,
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise AzureDevOpsError(
                f"Azure DevOps update Test Case {test_case_id} -> HTTP {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        data = resp.json()
        return {
            "id": data.get("id"),
            "url": data.get("url"),
            "title": data.get("fields", {}).get("System.Title"),
        }

    def _test_headers(self) -> Dict[str, str]:
        return {**self._auth, "Content-Type": "application/json"}

    def who_am_i(self) -> Dict[str, Any]:
        """Identidad del usuario dueño del PAT. Evita atribuir un 403 al código
        cuando en realidad el token pertenece a otra persona sin permisos."""
        try:
            resp = httpx.get(
                f"{settings.api_base}/_apis/ConnectionData",
                params={"api-version": "7.1-preview"},
                headers=self._auth,
                timeout=15.0,
            )
            if resp.status_code != 200:
                return {"ok": False, "error": f"HTTP {resp.status_code}"}
            user = (resp.json().get("authenticatedUser") or {})
            props = user.get("properties") or {}
            account = ((props.get("Account") or {}).get("$value")) if isinstance(props, dict) else None
            return {
                "ok": True,
                "display_name": user.get("providerDisplayName") or user.get("customDisplayName"),
                "account": account,
                "id": user.get("id"),
            }
        except httpx.HTTPError as exc:
            return {"ok": False, "error": str(exc)}

    def get_or_create_test_plan(self, plan_name: str) -> Dict[str, Any]:
        resp = httpx.get(
            self._url("/test/plans"),
            params={"api-version": "5.0"},
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
            # ID configurado pero no vino en la lista: intentar GET directo.
            direct = httpx.get(
                self._url(f"/test/plans/{settings.azure_devops_test_plan_id}"),
                params={"api-version": "5.0"},
                headers=self._auth,
                timeout=30.0,
            )
            if direct.status_code == 200:
                return direct.json()
            raise AzureDevOpsError(
                f"AZURE_DEVOPS_TEST_PLAN_ID={settings.azure_devops_test_plan_id} no existe "
                f"o no es accesible (HTTP {direct.status_code})."
            )
        for p in plans:
            if p.get("name") == plan_name:
                return p
        body = {
            "name": plan_name,
            "area": {"name": self._project},
            "iteration": self._project,
        }
        resp = httpx.post(
            self._url("/test/plans"),
            params={"api-version": "5.0"},
            headers=self._test_headers(),
            json=body,
            timeout=30.0,
        )
        if resp.status_code not in (200, 201):
            raise AzureDevOpsError(
                f"Test Plan create -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def get_root_suite(self, plan_id: int) -> Dict[str, Any]:
        resp = httpx.get(
            self._url(f"/testplan/Plans/{plan_id}/suites"),
            params={"api-version": "7.1-preview"},
            headers=self._auth,
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise AzureDevOpsError(
                f"Test Suites GET -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        suites = resp.json().get("value", [])
        for s in suites:
            if not s.get("parentSuite"):
                return s
        if suites:
            return suites[0]
        raise AzureDevOpsError("El Test Plan no tiene suites raíz.")

    def get_or_create_suite_for_hu(
        self, plan_id: int, root_suite_id: int, hu_id: int, hu_title: str = ""
    ) -> Dict[str, Any]:
        suite_name = f"HU #{hu_id}"
        if hu_title:
            clean = re.sub(r"\s+", " ", hu_title).strip()[:200]
            suite_name = f"HU #{hu_id} — {clean}"

        # API nueva "Test Plan" (7.1): la vieja (/test, 5.0) devuelve 403 en
        # escritura en muchas orgs aunque el PAT tenga full access.
        resp = httpx.get(
            self._url(f"/testplan/Plans/{plan_id}/suites"),
            params={"api-version": "7.1-preview"},
            headers=self._auth,
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise AzureDevOpsError(
                f"Test Suites GET -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        for s in resp.json().get("value", []):
            name = s.get("name") or ""
            if name == suite_name or name == f"HU #{hu_id}" or name.startswith(f"HU #{hu_id} "):
                return s

        body = {
            "name": suite_name,
            "suiteType": "staticTestSuite",
            "parentSuite": {"id": root_suite_id},
        }
        resp = httpx.post(
            self._url(f"/testplan/Plans/{plan_id}/suites"),
            params={"api-version": "7.1-preview"},
            headers=self._test_headers(),
            json=body,
            timeout=30.0,
        )
        if resp.status_code not in (200, 201):
            raise AzureDevOpsError(
                f"Crear suite de HU {hu_id} -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def _suite_test_case_ids(self, plan_id: int, suite_id: int) -> set:
        """IDs de casos ya presentes en la suite (para idempotencia)."""
        try:
            resp = httpx.get(
                self._url(f"/testplan/Plans/{plan_id}/Suites/{suite_id}/TestCase"),
                params={"api-version": "7.1-preview"},
                headers=self._auth,
                timeout=30.0,
            )
            if resp.status_code != 200:
                return set()
            ids = set()
            for item in resp.json().get("value", []):
                tc = item.get("testCase") or item.get("workItem") or {}
                tc_id = tc.get("id")
                if tc_id is not None:
                    ids.add(int(tc_id))
            return ids
        except (httpx.HTTPError, ValueError, TypeError):
            return set()

    def add_test_cases_to_suite(
        self, plan_id: int, suite_id: int, test_case_ids: List[int]
    ) -> Dict[str, Any]:
        """Agrega varios casos a la suite en una sola llamada (API testplan 7.1).
        Idempotente: omite los que ya están. Devuelve un reporte por caso."""
        existing = self._suite_test_case_ids(plan_id, suite_id)
        to_add = [int(i) for i in test_case_ids if int(i) not in existing]
        skipped = [int(i) for i in test_case_ids if int(i) in existing]
        added: List[int] = []
        error: Optional[str] = None

        if to_add:
            body = [{"workItem": {"id": i}} for i in to_add]
            resp = httpx.post(
                self._url(f"/testplan/Plans/{plan_id}/Suites/{suite_id}/TestCase"),
                params={"api-version": "7.1-preview"},
                headers=self._test_headers(),
                json=body,
                timeout=60.0,
            )
            if resp.status_code in (200, 201):
                added = to_add
            else:
                # Fallback a la API vieja /test caso por caso (reporte parcial).
                error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                for tc_id in to_add:
                    one = httpx.post(
                        self._url(f"/test/plans/{plan_id}/suites/{suite_id}/testcases/{tc_id}"),
                        params={"api-version": "5.0"},
                        headers=self._test_headers(),
                        timeout=30.0,
                    )
                    if one.status_code in (200, 201):
                        added.append(tc_id)
                if added:
                    error = None

        return {
            "added": added,
            "skipped": skipped,
            "failed": [i for i in to_add if i not in added],
            "error": error,
        }

    def add_test_case_to_suite(self, plan_id: int, suite_id: int, test_case_id: int) -> None:
        result = self.add_test_cases_to_suite(plan_id, suite_id, [test_case_id])
        if result["error"] and not result["added"] and not result["skipped"]:
            raise AzureDevOpsError(f"Add Test Case a suite -> {result['error']}")

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
        iteration_path: str = "",
        area_path: str = "",
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
        if iteration_path:
            fields["/fields/System.IterationPath"] = iteration_path
        if area_path:
            fields["/fields/System.AreaPath"] = area_path
        if steps_html:
            fields["/fields/Microsoft.VSTS.TCM.Steps"] = steps_html

        patch = [{"op": "add", "path": path, "value": value} for path, value in fields.items()]
        patch.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "Microsoft.VSTS.Common.TestedBy-Reverse",
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