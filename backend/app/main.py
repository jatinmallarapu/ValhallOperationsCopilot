"""Expose read-only asset queries and bounded SSE conversations."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .data import DataRepository
from .graph import build_graph, events
from .models import ChatRequest
from .rag import documents
from .tools import analyze


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository = DataRepository(Path(os.getenv("COPILOT_DATA", "data/demo.json")))
    docs = documents(Path("data/synthetic_docs"))
    app.state.repo = repository
    app.state.graph = build_graph(repository, docs, os.getenv("PROCEDURE_DATABASE_URL"))
    app.state.capacity = asyncio.Semaphore(4)
    yield


app = FastAPI(title="Valhall Ops Copilot", lifespan=lifespan)


@app.get("/api/health")
def health(request: Request) -> dict:
    repo = request.app.state.repo
    return {
        "status": "ok",
        "source": repo.corpus.source,
        "snapshot_at": repo.corpus.snapshot_at,
        "llm_provider": os.getenv("LLM_PROVIDER", "extractive"),
    }


@app.get("/api/assets")
def assets(request: Request) -> list[dict]:
    return [asset.model_dump() for asset in request.app.state.repo.corpus.assets]


@app.get("/api/assets/{ident}")
def asset(ident: str, request: Request) -> dict:
    repo = request.app.state.repo
    try:
        root = repo.find_asset(ident)
        return {
            **root.model_dump(),
            "children": [x.model_dump() for x in repo.get_children(ident)],
            "series": [
                {"id": s.id, "name": s.name, "unit": s.unit}
                for s in repo.get_timeseries_for_asset(ident)
            ],
        }
    except KeyError:
        raise HTTPException(404, "Unknown asset") from None


@app.get("/api/timeseries/{ident}")
def timeseries(
    ident: str, request: Request, start_ms: int | None = None, end_ms: int | None = None
) -> dict:
    try:
        series = request.app.state.repo.get_series(ident, start_ms, end_ms)
        return {**series.model_dump(), "statistics": analyze(series)}
    except KeyError:
        raise HTTPException(404, "Unknown time series") from None
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@app.post("/api/chat")
async def chat(data: ChatRequest, request: Request) -> StreamingResponse:
    repo = request.app.state.repo
    try:
        repo.find_asset(data.asset_id)
        if data.timeseries_id and data.timeseries_id not in {
            s.id for s in repo.get_timeseries_for_asset(data.asset_id)
        }:
            raise KeyError(data.timeseries_id)
    except KeyError:
        raise HTTPException(
            404, "Selected asset or sensor is outside the available scope"
        ) from None
    if data.start_ms is not None and data.end_ms is not None and data.start_ms >= data.end_ms:
        raise HTTPException(422, "start_ms must precede end_ms")

    async def stream():
        try:
            async with asyncio.timeout(45), request.app.state.capacity:
                async for event in events(request.app.state.graph, data, repo.corpus.source):
                    if await request.is_disconnected():
                        return
                    yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
        except TimeoutError:
            yield 'event: error\ndata: {"message":"The response exceeded its time budget."}\n\n'
        except (ValueError, OSError):
            yield 'event: error\ndata: {"message":"A tool could not read the selected evidence."}\n\n'

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# API routes are registered first so the static app cannot shadow them.
web = Path(os.getenv("COPILOT_WEB", "frontend/dist"))
if web.is_dir():
    app.mount("/", StaticFiles(directory=web, html=True), name="dashboard")
