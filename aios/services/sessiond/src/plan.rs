use aios_contracts::{TaskPlanGetRequest, TaskPlanPutRequest, TaskPlanRecord};

use crate::db::Database;

#[derive(Clone)]
pub struct TaskPlanStore {
    database: Database,
}

impl TaskPlanStore {
    pub fn new(database: Database) -> Self {
        Self { database }
    }

    pub fn put(&self, request: TaskPlanPutRequest) -> anyhow::Result<TaskPlanRecord> {
        self.database.put_task_plan(&request)
    }

    pub fn get(&self, request: TaskPlanGetRequest) -> anyhow::Result<Option<TaskPlanRecord>> {
        self.database.get_task_plan(&request)
    }
}
