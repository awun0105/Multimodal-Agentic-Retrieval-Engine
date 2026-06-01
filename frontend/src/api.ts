import type {
  AgentRun,
  Candidate,
  ExportPreview,
  FrameInfo,
  Session,
  SessionDetail,
  SearchOptions,
  SearchResponse,
  SearchResult
} from "./types";

const API_BASE = "/api";

export async function search(
  query: string,
  queryType: string,
  options: SearchOptions
): Promise<SearchResponse> {
  return post<SearchResponse>("/search", {
    query,
    query_type: queryType,
    limit: 50,
    object_filters: options.objectFilters
  });
}

export async function runAgent(query: string, queryType: string): Promise<AgentRun> {
  return post<AgentRun>("/agent/run", { query, query_type: queryType, limit: 10 });
}

export async function saveCandidate(
  result: SearchResult,
  sessionId: number | null
): Promise<Candidate> {
  return post<Candidate>("/candidates", {
    session_id: sessionId,
    video_id: result.video_id,
    frame_id: result.frame_id,
    timestamp: result.timestamp,
    rank: 0,
    answer: "",
    note: ""
  });
}

export async function updateCandidate(candidate: Candidate): Promise<Candidate> {
  return patch<Candidate>(`/candidates/${candidate.id}`, {
    answer: candidate.answer,
    rank: candidate.rank,
    note: candidate.note
  });
}

export async function createSession(title: string, queryType: string): Promise<Session> {
  return post<Session>("/sessions", { title, query_type: queryType });
}

export async function getSession(sessionId: number): Promise<SessionDetail> {
  const response = await fetch(`${API_BASE}/sessions/${sessionId}`);
  if (!response.ok) {
    throw new Error(`Failed to load session: ${response.status}`);
  }
  return response.json() as Promise<SessionDetail>;
}

export async function addClue(sessionId: number, text: string): Promise<SessionDetail> {
  await post("/sessions/" + sessionId + "/clues", { text });
  return getSession(sessionId);
}

export async function listCandidates(): Promise<Candidate[]> {
  const response = await fetch(`${API_BASE}/candidates`);
  if (!response.ok) {
    throw new Error(`Failed to load candidates: ${response.status}`);
  }
  return response.json() as Promise<Candidate[]>;
}

export async function validateExport(): Promise<{ valid: boolean; warnings: string[] }> {
  return post<{ valid: boolean; warnings: string[] }>("/validate", {});
}

export async function exportPreview(): Promise<ExportPreview> {
  return post<ExportPreview>("/export", {});
}

export async function listVideoFrames(videoId: string): Promise<FrameInfo[]> {
  const response = await fetch(`${API_BASE}/videos/${videoId}/frames`);
  if (!response.ok) {
    throw new Error(`Failed to load frames: ${response.status}`);
  }
  return response.json() as Promise<FrameInfo[]>;
}

export async function listObjectFilters(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/filters/objects`);
  if (!response.ok) {
    throw new Error(`Failed to load object filters: ${response.status}`);
  }
  return response.json() as Promise<string[]>;
}

async function post<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function patch<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}
