use aios_contracts::{
    EpisodicMemoryAppendRequest, EpisodicMemoryListRequest, EpisodicMemoryListResponse,
    EpisodicMemoryRecord, ProceduralMemoryListRequest, ProceduralMemoryListResponse,
    ProceduralMemoryPutRequest, ProceduralMemoryRecord, SemanticMemoryListRequest,
    SemanticMemoryListResponse, SemanticMemoryPutRequest, SemanticMemoryRecord,
    WorkingMemoryReadRequest, WorkingMemoryReadResponse, WorkingMemoryRecord,
    WorkingMemoryWriteRequest,
};

use crate::db::Database;

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct MemorySummary {
    pub working_refs: usize,
    pub episodic_entries: usize,
    pub semantic_slots: usize,
    pub procedural_rules: usize,
}

#[derive(Clone)]
pub struct WorkingMemoryStore {
    database: Database,
}

impl WorkingMemoryStore {
    pub fn new(database: Database) -> Self {
        Self { database }
    }

    pub fn write(&self, request: WorkingMemoryWriteRequest) -> anyhow::Result<WorkingMemoryRecord> {
        self.database.write_working_memory(&request)
    }

    pub fn read(
        &self,
        request: WorkingMemoryReadRequest,
    ) -> anyhow::Result<WorkingMemoryReadResponse> {
        self.database.read_working_memory(&request)
    }

    pub fn append_episodic(
        &self,
        request: EpisodicMemoryAppendRequest,
    ) -> anyhow::Result<EpisodicMemoryRecord> {
        self.database.append_episodic_memory(&request)
    }

    pub fn list_episodic(
        &self,
        request: EpisodicMemoryListRequest,
    ) -> anyhow::Result<EpisodicMemoryListResponse> {
        self.database.list_episodic_memory(&request)
    }

    pub fn put_semantic(
        &self,
        request: SemanticMemoryPutRequest,
    ) -> anyhow::Result<SemanticMemoryRecord> {
        self.database.put_semantic_memory(&request)
    }

    pub fn list_semantic(
        &self,
        request: SemanticMemoryListRequest,
    ) -> anyhow::Result<SemanticMemoryListResponse> {
        self.database.list_semantic_memory(&request)
    }

    pub fn put_procedural(
        &self,
        request: ProceduralMemoryPutRequest,
    ) -> anyhow::Result<ProceduralMemoryRecord> {
        self.database.put_procedural_memory(&request)
    }

    pub fn list_procedural(
        &self,
        request: ProceduralMemoryListRequest,
    ) -> anyhow::Result<ProceduralMemoryListResponse> {
        self.database.list_procedural_memory(&request)
    }
}
