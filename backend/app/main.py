import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .azure_client import AzureDevOpsError, azure_client
from .config import settings
from .llm_client import (
    LLMError,
    TestCaseGenerationError,
    generate_test_cases,
    steps_to_tcm_html,
)

app = FastAPI(title="QA Test Case Generator", version="1.0.0")


class GenerateRequest(BaseModel):
    work_item_id: int = Field(..., description="ID de la Historia de Usuario")
    quantity: int = Field(5, ge=1, le=50, description="Cantidad de casos esperados")
    instructions: str = Field(
        "", description="Instrucciones extra para el agente (tipos, prioridad, enfoque)"
    )


class TestCaseModel(BaseModel):
    title: str
    description: str = ""
    priority: int
    type: str
    preconditions: str
    steps: List[dict]


class CreateRequest(BaseModel):
    work_item_id: int
    test_cases: List[TestCaseModel]


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "model": settings.ollama_model,
        "azure_configured": bool(
            settings.azure_devops_org and settings.azure_devops_project and settings.azure_devops_pat
        ),
        "ollama_url": settings.ollama_url,
    }


@app.get("/api/hu/{work_item_id}")
def get_hu(work_item_id: int) -> dict:
    if not settings.azure_devops_org or not settings.azure_devops_project or not settings.azure_devops_pat:
        raise HTTPException(status_code=400, detail="Configura AZURE_DEVOPS_* en el archivo .env")
    try:
        return azure_client.get_work_item(work_item_id)
    except AzureDevOpsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    if not settings.azure_devops_org or not settings.azure_devops_project or not settings.azure_devops_pat:
        raise HTTPException(status_code=400, detail="Configura AZURE_DEVOPS_* en el archivo .env")

    try:
        work_item = azure_client.get_work_item(req.work_item_id)
    except AzureDevOpsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if (work_item.get("type") or "").lower() not in ("user story", "hu", "story", "feature", ""):
        pass  # aceptamos cualquier tipo por flexibilidad

    try:
        result = generate_test_cases(work_item, req.quantity, req.instructions)
    except (LLMError, TestCaseGenerationError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"work_item": work_item, **result}


@app.post("/api/create")
def create(req: CreateRequest) -> dict:
    if not settings.azure_devops_org or not settings.azure_devops_project or not settings.azure_devops_pat:
        raise HTTPException(status_code=400, detail="Configura AZURE_DEVOPS_* en el archivo .env")

    created = []
    for tc in req.test_cases:
        steps_html = steps_to_tcm_html(
            [{"action": s.get("action", ""), "expected": s.get("expected", "")} for s in tc.steps]
        )
        try:
            item = azure_client.create_test_case(
                title=tc.title,
                description=tc.description,
                steps_html=steps_html,
                user_story_id=req.work_item_id,
            )
            created.append(item)
        except AzureDevOpsError as exc:
            return {"created": created, "error": str(exc)}

    return {"created": created, "count": len(created), "linked_to_work_item": req.work_item_id}


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "static"), html=True), name="static")