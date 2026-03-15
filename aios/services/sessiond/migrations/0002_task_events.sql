CREATE TABLE IF NOT EXISTS task_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
