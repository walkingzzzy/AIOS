use aios_contracts::{
    TaskCreateRequest, TaskEventListRequest, TaskEventListResponse, TaskGetRequest,
    TaskListRequest, TaskListResponse, TaskRecord, TaskStateUpdateRequest,
};

use crate::db::Database;

#[derive(Clone)]
pub struct TaskStore {
    database: Database,
}

impl TaskStore {
    pub fn new(database: Database) -> Self {
        Self { database }
    }

    pub fn create(&self, request: TaskCreateRequest) -> anyhow::Result<TaskRecord> {
        self.database.create_task(&request)
    }

    pub fn get(&self, request: TaskGetRequest) -> anyhow::Result<Option<TaskRecord>> {
        self.database.get_task(&request)
    }

    pub fn list(&self, request: TaskListRequest) -> anyhow::Result<TaskListResponse> {
        self.database.list_tasks(&request)
    }

    pub fn update_state(
        &self,
        request: TaskStateUpdateRequest,
    ) -> anyhow::Result<Option<TaskRecord>> {
        self.database.update_task_state(&request)
    }

    pub fn list_events(
        &self,
        request: TaskEventListRequest,
    ) -> anyhow::Result<TaskEventListResponse> {
        self.database.list_task_events(&request)
    }
}
