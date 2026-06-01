from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    query_type: str = "tkis"
    limit: int = Field(default=50, ge=1, le=200)


class SearchResult(BaseModel):
    video_id: str
    frame_id: int
    timestamp: float
    thumb_url: str | None
    keyframe_url: str | None
    score: float
    evidence: list[str]


class SearchResponse(BaseModel):
    query: str
    query_type: str
    results: list[SearchResult]


class DatasetInfo(BaseModel):
    id: str
    name: str
    video_count: int
    frame_count: int


class VideoInfo(BaseModel):
    video_id: str
    path: str
    fps: float | None
    duration: float | None
    width: int | None
    height: int | None


class FrameInfo(BaseModel):
    video_id: str
    frame_id: int
    timestamp: float
    thumb_url: str | None
    keyframe_url: str | None
    caption: str


class SessionCreate(BaseModel):
    query_type: str = "tkis"
    title: str


class Session(BaseModel):
    id: int
    query_type: str
    title: str
    created_at: str


class ClueCreate(BaseModel):
    text: str = Field(min_length=1)


class CandidateCreate(BaseModel):
    session_id: int | None = None
    video_id: str
    frame_id: int
    timestamp: float
    answer: str = ""
    rank: int = 0
    note: str = ""


class Candidate(CandidateCreate):
    id: int
    created_at: str


class AgentRunRequest(BaseModel):
    query: str = Field(min_length=1)
    query_type: str = "auto"
    session_id: int | None = None
    limit: int = Field(default=10, ge=1, le=50)


class AgentStep(BaseModel):
    step_index: int
    tool: str
    input: dict
    output: dict
    latency_ms: int = 0


class AgentRunResponse(BaseModel):
    run_id: int
    status: str
    route: str
    confidence: float
    results: list[SearchResult]
    steps: list[AgentStep]


class ValidationResponse(BaseModel):
    valid: bool
    warnings: list[str]
    row_count: int


class ExportRow(BaseModel):
    video_id: str
    frame_id: int
    answer: str


class ExportResponse(BaseModel):
    format: str
    rows: list[ExportRow]
