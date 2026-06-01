import { Bot, CheckCircle2, Film, Pin, Search, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listCandidates, runAgent, saveCandidate, search, validateExport } from "./api";
import type { AgentRun, Candidate, SearchResult } from "./types";

const queryTypes = ["tkis", "qa", "trake", "vkis"];

export function App() {
  const [query, setQuery] = useState("lantern city festival");
  const [queryType, setQueryType] = useState("tkis");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [agentRun, setAgentRun] = useState<AgentRun | null>(null);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refreshCandidates();
  }, []);

  const evidence = useMemo(() => selected?.evidence.join(" | ") || "No evidence selected", [selected]);

  async function refreshCandidates() {
    setCandidates(await listCandidates());
  }

  async function handleSearch() {
    setError(null);
    setStatus("Searching");
    try {
      const response = await search(query, queryType);
      setResults(response.results);
      setSelected(response.results[0] ?? null);
      setStatus(`Found ${response.results.length} results`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
      setStatus("Error");
    }
  }

  async function handleAgentRun() {
    setError(null);
    setStatus("Agent running");
    try {
      const response = await runAgent(query, queryType);
      setAgentRun(response);
      setResults(response.results);
      setSelected(response.results[0] ?? null);
      setStatus(`Agent completed: ${response.route}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent run failed");
      setStatus("Error");
    }
  }

  async function handleSave(result: SearchResult) {
    await saveCandidate(result);
    await refreshCandidates();
  }

  async function handleValidate() {
    const response = await validateExport();
    setStatus(response.valid ? "Export preview valid" : "Export has issues");
    if (response.warnings.length > 0) {
      setError(response.warnings.join(" "));
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <Film size={20} />
          <span>AIC Retrieval</span>
        </div>
        <form
          className="searchbar"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSearch();
          }}
        >
          <select value={queryType} onChange={(event) => setQueryType(event.target.value)}>
            {queryTypes.map((type) => (
              <option key={type} value={type}>
                {type.toUpperCase()}
              </option>
            ))}
          </select>
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
          <button type="submit">
            <Search size={16} />
            Search
          </button>
          <button type="button" className="secondary" onClick={() => void handleAgentRun()}>
            <Bot size={16} />
            Agent
          </button>
        </form>
        <div className="status">{status}</div>
      </header>

      <aside className="sidebar">
        <section>
          <h2>Modes</h2>
          <div className="mode active">Interactive</div>
          <div className="mode">Automatic agent</div>
        </section>
        <section>
          <h2>Saved</h2>
          {candidates.length === 0 ? (
            <p className="muted">No candidates saved.</p>
          ) : (
            candidates.map((candidate) => (
              <div className="saved" key={candidate.id}>
                <strong>{candidate.video_id}</strong>
                <span>Frame {candidate.frame_id}</span>
              </div>
            ))
          )}
        </section>
      </aside>

      <main className="results">
        <div className="panel-title">
          <SlidersHorizontal size={16} />
          <span>Frame Results</span>
        </div>
        {error ? <div className="error">{error}</div> : null}
        <div className="grid">
          {results.map((result) => (
            <button
              key={`${result.video_id}-${result.frame_id}`}
              className={`card ${
                selected?.video_id === result.video_id && selected.frame_id === result.frame_id
                  ? "selected"
                  : ""
              }`}
              onClick={() => setSelected(result)}
            >
              <div className="thumb">
                {result.thumb_url ? (
                  <img src={result.thumb_url} alt={`${result.video_id} frame ${result.frame_id}`} />
                ) : (
                  <span>No thumbnail</span>
                )}
              </div>
              <div className="card-meta">
                <strong>{result.video_id}</strong>
                <span>Frame {result.frame_id}</span>
                <span>{result.timestamp.toFixed(2)}s</span>
                <span>{Math.round(result.score * 100)}%</span>
              </div>
            </button>
          ))}
        </div>
      </main>

      <aside className="inspector">
        <h2>Inspector</h2>
        {selected ? (
          <>
            <div className="preview">
              {selected.keyframe_url ? (
                <img src={selected.keyframe_url} alt="Selected keyframe" />
              ) : (
                <span>Keyframe unavailable</span>
              )}
            </div>
            <dl>
              <dt>Video</dt>
              <dd>{selected.video_id}</dd>
              <dt>Frame</dt>
              <dd>{selected.frame_id}</dd>
              <dt>Timestamp</dt>
              <dd>{selected.timestamp.toFixed(2)}s</dd>
              <dt>Evidence</dt>
              <dd>{evidence}</dd>
            </dl>
            <button className="wide" onClick={() => void handleSave(selected)}>
              <Pin size={16} />
              Save candidate
            </button>
          </>
        ) : (
          <p className="muted">Run a search and select a result.</p>
        )}

        <section className="agent">
          <h2>Automatic Mode</h2>
          {agentRun ? (
            <>
              <p>
                Route <strong>{agentRun.route}</strong> · confidence{" "}
                {Math.round(agentRun.confidence * 100)}%
              </p>
              {agentRun.steps.map((step) => (
                <div className="trace" key={step.step_index}>
                  <span>{step.tool}</span>
                  <span>{step.latency_ms} ms</span>
                </div>
              ))}
            </>
          ) : (
            <p className="muted">Run the agent to inspect its route and tool calls.</p>
          )}
        </section>

        <button className="wide secondary" onClick={() => void handleValidate()}>
          <CheckCircle2 size={16} />
          Validate export
        </button>
      </aside>
    </div>
  );
}
