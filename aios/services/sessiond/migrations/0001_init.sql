CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    last_resumed_at TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    title TEXT,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS task_plans (
    task_id TEXT PRIMARY KEY,
    plan_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS memory_working_refs (
    ref_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS memory_episodic_entries (
    entry_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS memory_semantic_indexes (
    index_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    label TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS memory_procedural_versions (
    version_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS portal_handles (
    handle_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    scope_json TEXT,
    expiry TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS recovery_refs (
    recovery_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
);
