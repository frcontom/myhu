import base64
import re
from typing import Any, Dict, List

import httpx

from .config import settings


def parse_criteria(text: str) -> List[str]:
    if not text:
        return []
    lines = [
        re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        for line in text.splitlines()
    ]
    return [line for line in lines if line]


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
        acceptance_criteria = fields.get("Microsoft.VSTS.Common.AcceptanceCriteria")
        return {
            "id": data.get("id"),
            "type": fields.get("System.WorkItemType"),
            "title": fields.get("System.Title"),
            "description": fields.get("System.Description"),
            "acceptance_criteria": acceptance_criteria,
            "criteria_list": parse_criteria(acceptance_criteria),
            "state": fields.get("System.State"),
            "created_by": fields.get("System.CreatedBy", {}).get("displayName"),
        }

    def get_work_item_url(self, work_item_id: int) -> str:
        return f"{settings.api_base}/{self._project}/_apis/wit/workItems/{work_item_id}"

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
    ) -> Dict[str, Any]:
        fields: Dict[str, Any] = {
            "/fields/System.Title": title,
        }
        if description:
            fields["/fields/System.Description"] = description
        if priority:
            fields["/fields/Microsoft.VSTS.Common.Priority"] = priority
        if steps_html:
            fields["/fields/Microsoft.VSTS.TCM.Steps"] = steps_html

        patch = [{"op": "add", "path": path, "value": value} for path, value in fields.items()]
        patch.append(
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "Microsoft.VSTS.Common.Tests",
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