from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import Settings, get_settings
from .db import connect, init_db
from .demo_data import seed_demo_data
from .models import (
    AgentRunRequest,
    AgentRunResponse,
    AgentStep,
    Candidate,
    CandidateCreate,
    ClueCreate,
    DatasetInfo,
    ExportResponse,
    ExportRow,
    FrameInfo,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    Session,
    SessionCreate,
    ValidationResponse,
    VideoInfo,
)
from .search import search_frames


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_db(settings.database_path)
    with connect(settings.database_path) as connection:
        seed_demo_data(connection)
    yield


app = FastAPI(title="AIC Retrieval API", lifespan=lifespan)


settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@app.get("/datasets", response_model=list[DatasetInfo])
def list_datasets(settings: Settings = Depends(get_settings)) -> list[DatasetInfo]:
    with connect(settings.database_path) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM videos) AS video_count,
              (SELECT COUNT(*) FROM frames) AS frame_count
            """
        ).fetchone()
    return [
        DatasetInfo(
            id="default",
            name="Default local dataset",
            video_count=counts["video_count"],
            frame_count=counts["frame_count"],
        )
    ]


@app.get("/videos", response_model=list[VideoInfo])
def list_videos(settings: Settings = Depends(get_settings)) -> list[VideoInfo]:
    with connect(settings.database_path) as connection:
        rows = connection.execute("SELECT * FROM videos ORDER BY video_id").fetchall()
    return [VideoInfo(**dict(row)) for row in rows]


@app.get("/videos/{video_id}", response_model=VideoInfo)
def get_video(video_id: str, settings: Settings = Depends(get_settings)) -> VideoInfo:
    with connect(settings.database_path) as connection:
        row = connection.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return VideoInfo(**dict(row))


@app.get("/videos/{video_id}/frames", response_model=list[FrameInfo])
def list_video_frames(
    video_id: str, limit: int = 200, settings: Settings = Depends(get_settings)
) -> list[FrameInfo]:
    with connect(settings.database_path) as connection:
        rows = connection.execute(
            """
            SELECT video_id, frame_id, timestamp, thumb_path, keyframe_path, caption
            FROM frames
            WHERE video_id=?
            ORDER BY frame_id
            LIMIT ?
            """,
            (video_id, limit),
        ).fetchall()
    return [
        FrameInfo(
            video_id=row["video_id"],
            frame_id=row["frame_id"],
            timestamp=row["timestamp"],
            thumb_url=f"/media/thumbs/{row['video_id']}/{row['frame_id']}"
            if row["thumb_path"]
            else None,
            keyframe_url=f"/media/keyframes/{row['video_id']}/{row['frame_id']}"
            if row["keyframe_path"]
            else None,
            caption=row["caption"],
        )
        for row in rows
    ]


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, settings: Settings = Depends(get_settings)) -> SearchResponse:
    with connect(settings.database_path) as connection:
        results = search_frames(connection, request.query, request.limit)
    return SearchResponse(query=request.query, query_type=request.query_type, results=results)


@app.get("/media/{kind}/{video_id}/{frame_id}")
def get_frame_media(
    kind: str, video_id: str, frame_id: int, settings: Settings = Depends(get_settings)
) -> FileResponse:
    if kind not in {"thumbs", "keyframes"}:
        raise HTTPException(status_code=404, detail="Unsupported media kind")

    with connect(settings.database_path) as connection:
        row = connection.execute(
            "SELECT thumb_path, keyframe_path FROM frames WHERE video_id=? AND frame_id=?",
            (video_id, frame_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Frame not found")

    relative_path = row["thumb_path"] if kind == "thumbs" else row["keyframe_path"]
    path = settings.data_root / relative_path
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Media file missing: {path}")
    return FileResponse(path)


@app.post("/sessions", response_model=Session)
def create_session(
    request: SessionCreate, settings: Settings = Depends(get_settings)
) -> Session:
    with connect(settings.database_path) as connection:
        cursor = connection.execute(
            "INSERT INTO query_sessions(query_type, title) VALUES (?, ?)",
            (request.query_type, request.title),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id, query_type, title, created_at FROM query_sessions WHERE id=?",
            (cursor.lastrowid,),
        ).fetchone()
    return Session(**dict(row))


@app.post("/sessions/{session_id}/clues")
def add_clue(
    session_id: int, request: ClueCreate, settings: Settings = Depends(get_settings)
) -> dict[str, int]:
    with connect(settings.database_path) as connection:
        exists = connection.execute(
            "SELECT id FROM query_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Session not found")
        next_index = connection.execute(
            "SELECT COALESCE(MAX(order_index), 0) + 1 AS next_index FROM query_clues WHERE session_id=?",
            (session_id,),
        ).fetchone()["next_index"]
        cursor = connection.execute(
            "INSERT INTO query_clues(session_id, text, order_index) VALUES (?, ?, ?)",
            (session_id, request.text, next_index),
        )
        connection.commit()
    return {"id": int(cursor.lastrowid), "order_index": int(next_index)}


@app.post("/candidates", response_model=Candidate)
def save_candidate(
    request: CandidateCreate, settings: Settings = Depends(get_settings)
) -> Candidate:
    with connect(settings.database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO candidates(session_id, video_id, frame_id, timestamp, answer, rank, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.session_id,
                request.video_id,
                request.frame_id,
                request.timestamp,
                request.answer,
                request.rank,
                request.note,
            ),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM candidates WHERE id=?", (cursor.lastrowid,)).fetchone()
    return Candidate(**dict(row))


@app.get("/candidates", response_model=list[Candidate])
def list_candidates(settings: Settings = Depends(get_settings)) -> list[Candidate]:
    with connect(settings.database_path) as connection:
        rows = connection.execute("SELECT * FROM candidates ORDER BY id DESC").fetchall()
    return [Candidate(**dict(row)) for row in rows]


@app.post("/agent/run", response_model=AgentRunResponse)
def run_agent(
    request: AgentRunRequest, settings: Settings = Depends(get_settings)
) -> AgentRunResponse:
    route = request.query_type if request.query_type != "auto" else _route_query(request.query)
    started = time.perf_counter()
    with connect(settings.database_path) as connection:
        results = search_frames(connection, request.query, request.limit)
        confidence = results[0].score if results else 0.0
        cursor = connection.execute(
            """
            INSERT INTO agent_runs(session_id, status, query, route, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request.session_id, "completed", request.query, route, confidence),
        )
        run_id = int(cursor.lastrowid)
        step = AgentStep(
            step_index=1,
            tool="search",
            input={"query": request.query, "limit": request.limit},
            output={"result_count": len(results), "route": route},
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        connection.execute(
            """
            INSERT INTO agent_steps(run_id, step_index, tool, input_json, output_json, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                step.step_index,
                step.tool,
                json.dumps(step.input),
                json.dumps(step.output),
                step.latency_ms,
            ),
        )
        connection.commit()
    return AgentRunResponse(
        run_id=run_id,
        status="completed",
        route=route,
        confidence=confidence,
        results=results,
        steps=[step],
    )


@app.get("/agent/runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run(run_id: int, settings: Settings = Depends(get_settings)) -> AgentRunResponse:
    with connect(settings.database_path) as connection:
        run = connection.execute("SELECT * FROM agent_runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="Agent run not found")
        step_rows = connection.execute(
            "SELECT * FROM agent_steps WHERE run_id=? ORDER BY step_index", (run_id,)
        ).fetchall()
        results = search_frames(connection, run["query"], 10)
    steps = [
        AgentStep(
            step_index=row["step_index"],
            tool=row["tool"],
            input=json.loads(row["input_json"]),
            output=json.loads(row["output_json"]),
            latency_ms=row["latency_ms"],
        )
        for row in step_rows
    ]
    return AgentRunResponse(
        run_id=run_id,
        status=run["status"],
        route=run["route"],
        confidence=run["confidence"],
        results=results,
        steps=steps,
    )


@app.post("/validate", response_model=ValidationResponse)
def validate_export(settings: Settings = Depends(get_settings)) -> ValidationResponse:
    with connect(settings.database_path) as connection:
        row_count = connection.execute("SELECT COUNT(*) AS count FROM candidates").fetchone()["count"]
    return ValidationResponse(
        valid=True,
        warnings=["Official 2026 rules are not configured yet."],
        row_count=row_count,
    )


@app.post("/export", response_model=ExportResponse)
def export_candidates(settings: Settings = Depends(get_settings)) -> ExportResponse:
    with connect(settings.database_path) as connection:
        rows = connection.execute("SELECT * FROM candidates ORDER BY rank, id").fetchall()
    return ExportResponse(
        format="preview",
        rows=[
            ExportRow(video_id=row["video_id"], frame_id=row["frame_id"], answer=row["answer"])
            for row in rows
        ],
    )


def _route_query(query: str) -> str:
    lowered = query.lower()
    if "e1" in lowered or "e2" in lowered or "event" in lowered:
        return "trake"
    if "?" in query or "hỏi" in lowered or "answer" in lowered:
        return "qa"
    return "tkis"
