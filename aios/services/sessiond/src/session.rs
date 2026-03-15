use aios_contracts::{
    SessionCloseRequest, SessionCreateRequest, SessionListRequest, SessionListResponse,
    SessionRecord, SessionResumeRequest,
};

use crate::db::Database;

#[derive(Clone)]
pub struct SessionStore {
    database: Database,
}

impl SessionStore {
    pub fn new(database: Database) -> Self {
        Self { database }
    }

    pub fn create(&self, request: SessionCreateRequest) -> anyhow::Result<SessionRecord> {
        self.database.create_session(&request)
    }

    pub fn resume(&self, request: SessionResumeRequest) -> anyhow::Result<Option<SessionRecord>> {
        self.database.resume_session(&request)
    }

    pub fn close(&self, request: SessionCloseRequest) -> anyhow::Result<Option<SessionRecord>> {
        self.database.close_session(&request)
    }

    pub fn list(&self, request: SessionListRequest) -> anyhow::Result<SessionListResponse> {
        self.database.list_sessions(&request)
    }

    pub fn get(&self, session_id: &str) -> anyhow::Result<Option<SessionRecord>> {
        self.database.get_session(session_id)
    }
}
