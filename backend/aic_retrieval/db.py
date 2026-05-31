from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  fps REAL,
  duration REAL,
  width INTEGER,
  height INTEGER
);

CREATE TABLE IF NOT EXISTS frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  timestamp REAL NOT NULL,
  thumb_path TEXT,
  keyframe_path TEXT,
  caption TEXT DEFAULT '',
  UNIQUE(video_id, frame_id),
  FOREIGN KEY(video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS objects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  score REAL DEFAULT 0,
  box_json TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  frame_id INTEGER,
  type TEXT NOT NULL,
  text TEXT NOT NULL,
  score REAL DEFAULT 0,
  source TEXT DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS frame_search USING fts5(
  video_id UNINDEXED,
  frame_id UNINDEXED,
  text
);

CREATE TABLE IF NOT EXISTS query_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query_type TEXT NOT NULL,
  title TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS query_clues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL,
  text TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  FOREIGN KEY(session_id) REFERENCES query_sessions(id)
);

CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER,
  video_id TEXT NOT NULL,
  frame_id INTEGER NOT NULL,
  timestamp REAL NOT NULL,
  answer TEXT DEFAULT '',
  rank INTEGER DEFAULT 0,
  note TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER,
  status TEXT NOT NULL,
  query TEXT NOT NULL,
  route TEXT NOT NULL,
  confidence REAL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  step_index INTEGER NOT NULL,
  tool TEXT NOT NULL,
  input_json TEXT NOT NULL,
  output_json TEXT NOT NULL,
  latency_ms INTEGER DEFAULT 0,
  FOREIGN KEY(run_id) REFERENCES agent_runs(id)
);
"""


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db(database_path: Path) -> None:
    with connect(database_path) as connection:
        connection.executescript(SCHEMA)


def get_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(database_path)
    try:
        yield connection
    finally:
        connection.close()

