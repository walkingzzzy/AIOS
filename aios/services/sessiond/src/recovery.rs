use aios_contracts::RecoveryRef;

use crate::db::Database;

pub fn baseline_ref(database: &Database, session_id: &str) -> anyhow::Result<RecoveryRef> {
    database.recovery_ref(session_id)
}
