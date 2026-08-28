import json
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .azure_client import AzureDevOpsError, azure_client, sample_work_item
from .config import settings
from .llm_client import (
    LLMError,
    TestCaseGenerationError,
    generate_test_cases,
    steps_to_tcm_html,
    stream_test_cases,
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
        "azure_configured": settings.is_configured,
        "demo_mode": settings.demo_mode,
        "ollama_url": settings.ollama_url,
    }


@app.get("/api/test-azure")
def test_azure() -> dict:
    if not settings.is_configured:
        raise HTTPException(status_code=400, detail="Configura AZURE_DEVOPS_* en el archivo .env")
    try:
        return azure_client.test_connection()
    except AzureDevOpsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/hu/{work_item_id}")
def get_hu(work_item_id: int) -> dict:
    if settings.demo_mode:
        return sample_work_item(work_item_id)
    if not settings.is_configured:
        raise HTTPException(status_code=400, detail="Configura AZURE_DEVOPS_* en el archivo .env")
    try:
        return azure_client.get_work_item(work_item_id)
    except AzureDevOpsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/generate-stream")
def generate_stream(
    work_item_id: int,
    quantity: int = 5,
    instructions: str = "",
):
    quantity = max(1, min(quantity, 50))

    def event_stream():
        if settings.demo_mode:
            work_item = sample_work_item(work_item_id)
        else:
            if not settings.is_configured:
                yield _sse("error", {"detail": "Configura AZURE_DEVOPS_* en el archivo .env"})
                return
            try:
                work_item = azure_client.get_work_item(work_item_id)
            except AzureDevOpsError as exc:
                yield _sse("error", {"detail": str(exc)})
                return
        try:
            for ev in stream_test_cases(work_item, quantity, instructions):
                if ev["type"] == "done":
                    ev["data"]["work_item"] = work_item
                yield _sse(ev["type"], ev["data"])
        except Exception as exc:
            yield _sse("error", {"detail": f"Error interno: {exc}"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/generate")
def generate(req: GenerateRequest) -> dict:
    if settings.demo_mode:
        work_item = sample_work_item(req.work_item_id)
    else:
        if not settings.is_configured:
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
    if settings.demo_mode:
        created = [
            {
                "id": f"demo-{i + 1}",
                "url": None,
                "title": tc.title,
            }
            for i, tc in enumerate(req.test_cases)
        ]
        return {
            "created": created,
            "count": len(created),
            "linked_to_work_item": req.work_item_id,
            "demo": True,
        }

    if not settings.is_configured:
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
                priority=tc.priority,
            )
            created.append(item)
        except AzureDevOpsError as exc:
            return {"created": created, "error": str(exc)}

    return {"created": created, "count": len(created), "linked_to_work_item": req.work_item_id}


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "static"), html=True), name="static")