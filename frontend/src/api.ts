import type { AgentRun, Candidate, ExportPreview, FrameInfo, SearchResponse, SearchResult } from "./types";

const API_BASE = "/api";

export async function search(query: string, queryType: string): Promise<SearchResponse> {
  return post<SearchResponse>("/search", { query, query_type: queryType, limit: 50 });
}

export async function runAgent(query: string, queryType: string): Promise<AgentRun> {
  return post<AgentRun>("/agent/run", { query, query_type: queryType, limit: 10 });
}

export async function saveCandidate(result: SearchResult): Promise<Candidate> {
  return post<Candidate>("/candidates", {
    video_id: result.video_id,
    frame_id: result.frame_id,
    timestamp: result.timestamp,
    rank: 0,
    answer: "",
    note: ""
  });
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
