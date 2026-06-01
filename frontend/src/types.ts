export type SearchResult = {
  video_id: string;
  frame_id: number;
  timestamp: number;
  thumb_url: string | null;
  keyframe_url: string | null;
  score: number;
  evidence: string[];
};

export type SearchResponse = {
  query: string;
  query_type: string;
  results: SearchResult[];
};

export type Candidate = {
  id: number;
  session_id: number | null;
  video_id: string;
  frame_id: number;
  timestamp: number;
  answer: string;
  rank: number;
  note: string;
  created_at: string;
};

export type AgentRun = {
  run_id: number;
  status: string;
  route: string;
  confidence: number;
  results: SearchResult[];
  steps: Array<{
    step_index: number;
    tool: string;
    input: Record<string, unknown>;
    output: Record<string, unknown>;
    latency_ms: number;
  }>;
};

export type FrameInfo = {
  video_id: string;
  frame_id: number;
  timestamp: number;
  thumb_url: string | null;
  keyframe_url: string | null;
  caption: string;
};

export type ExportPreview = {
  format: string;
  rows: Array<{
    video_id: string;
    frame_id: number;
    answer: string;
  }>;
};
