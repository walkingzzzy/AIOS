use aios_contracts::{
    PortalHandleRecord, PortalIssueHandleRequest, PortalListHandlesRequest,
    PortalListHandlesResponse, PortalLookupHandleRequest, PortalLookupHandleResponse,
    PortalRevokeHandleRequest,
};
use aios_portal::Portal;

use crate::db::Database;

#[derive(Clone)]
pub struct PortalStore {
    database: Database,
    portal: Portal,
}

impl PortalStore {
    pub fn new(database: Database, portal: Portal) -> Self {
        Self { database, portal }
    }

    pub fn issue(&self, request: PortalIssueHandleRequest) -> anyhow::Result<PortalHandleRecord> {
        let handle = self.portal.issue_handle(&request)?;
        self.database.bind_portal_handle(&handle)?;
        Ok(handle)
    }

    pub fn lookup(
        &self,
        request: PortalLookupHandleRequest,
    ) -> anyhow::Result<PortalLookupHandleResponse> {
        let response = self.portal.lookup_handle(&request)?;
        if let Some(handle) = &response.handle {
            self.database.bind_portal_handle(handle)?;
        }

        Ok(response)
    }

    pub fn revoke(
        &self,
        request: PortalRevokeHandleRequest,
    ) -> anyhow::Result<PortalLookupHandleResponse> {
        let existing = self.portal.lookup_handle(&PortalLookupHandleRequest {
            handle_id: request.handle_id.clone(),
            session_id: request.session_id.clone(),
            user_id: request.user_id.clone(),
        })?;
        if existing.handle.is_none() {
            return Ok(PortalLookupHandleResponse { handle: None });
        }

        let response = self.portal.revoke_handle(&request)?;
        if let Some(handle) = &response.handle {
            self.database.bind_portal_handle(handle)?;
        }

        Ok(response)
    }

    pub fn list(
        &self,
        request: PortalListHandlesRequest,
    ) -> anyhow::Result<PortalListHandlesResponse> {
        let response = self.portal.list_handles(request.session_id.as_deref())?;
        for handle in &response.handles {
            self.database.bind_portal_handle(handle)?;
        }

        Ok(response)
    }

    pub fn from_database(
        &self,
        request: PortalListHandlesRequest,
    ) -> anyhow::Result<PortalListHandlesResponse> {
        self.database
            .list_portal_handles(request.session_id.as_deref())
    }
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use serde_json::json;

    use aios_contracts::{
        PortalIssueHandleRequest, PortalLookupHandleRequest, PortalRevokeHandleRequest,
        SessionCreateRequest,
    };
    use aios_portal::{Portal, PortalConfig};

    use super::PortalStore;
    use crate::db::Database;

    fn temp_root(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "aios-sessiond-portal-{name}-{}",
            uuid::Uuid::new_v4().simple()
        ));
        std::fs::create_dir_all(&root).expect("create temp root");
        root
    }

    fn build_store(root: &std::path::Path) -> anyhow::Result<PortalStore> {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let database = Database::new(
            root.join("sessiond.sqlite3"),
            manifest_dir.join("migrations"),
        );
        database.apply_migrations()?;
        let portal = Portal::new(PortalConfig {
            state_dir: root.join("portal"),
            default_ttl_seconds: 60,
        })?;
        Ok(PortalStore::new(database, portal))
    }

    fn issue_request(user_id: &str, session_id: &str, target: &str) -> PortalIssueHandleRequest {
        PortalIssueHandleRequest {
            kind: "file_handle".to_string(),
            user_id: user_id.to_string(),
            session_id: session_id.to_string(),
            target: target.to_string(),
            scope: std::collections::BTreeMap::from([(
                "display_name".to_string(),
                json!("demo.txt"),
            )]),
            expiry_seconds: Some(60),
            revocable: true,
            audit_tags: vec!["portal".to_string(), "test".to_string()],
        }
    }

    fn create_session(store: &PortalStore, user_id: &str) -> anyhow::Result<String> {
        Ok(store
            .database
            .create_session(&SessionCreateRequest {
                user_id: user_id.to_string(),
                metadata: std::collections::BTreeMap::new(),
            })?
            .session_id)
    }

    #[test]
    fn lookup_hides_handle_when_session_or_user_mismatch() -> anyhow::Result<()> {
        let root = temp_root("lookup-context");
        let store = build_store(&root)?;
        let session_id = create_session(&store, "user-1")?;
        let target = root.join("demo.txt");
        std::fs::write(&target, "demo")?;
        let handle = store.issue(issue_request(
            "user-1",
            &session_id,
            &target.display().to_string(),
        ))?;

        let same_context = store.lookup(PortalLookupHandleRequest {
            handle_id: handle.handle_id.clone(),
            session_id: Some(session_id.clone()),
            user_id: Some("user-1".to_string()),
        })?;
        assert!(same_context.handle.is_some());

        let wrong_session = store.lookup(PortalLookupHandleRequest {
            handle_id: handle.handle_id.clone(),
            session_id: Some("session-2".to_string()),
            user_id: Some("user-1".to_string()),
        })?;
        assert!(wrong_session.handle.is_none());

        let wrong_user = store.lookup(PortalLookupHandleRequest {
            handle_id: handle.handle_id,
            session_id: Some(session_id),
            user_id: Some("user-2".to_string()),
        })?;
        assert!(wrong_user.handle.is_none());

        let _ = std::fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn revoke_requires_matching_context_before_updating_handle() -> anyhow::Result<()> {
        let root = temp_root("revoke-context");
        let store = build_store(&root)?;
        let session_id = create_session(&store, "user-1")?;
        let target = root.join("demo.txt");
        std::fs::write(&target, "demo")?;
        let handle = store.issue(issue_request(
            "user-1",
            &session_id,
            &target.display().to_string(),
        ))?;

        let blocked = store.revoke(PortalRevokeHandleRequest {
            handle_id: handle.handle_id.clone(),
            session_id: Some("session-2".to_string()),
            user_id: Some("user-1".to_string()),
            reason: Some("should not work".to_string()),
        })?;
        assert!(blocked.handle.is_none());

        let still_active = store.lookup(PortalLookupHandleRequest {
            handle_id: handle.handle_id.clone(),
            session_id: Some(session_id.clone()),
            user_id: Some("user-1".to_string()),
        })?;
        assert!(still_active
            .handle
            .as_ref()
            .is_some_and(|record| record.revoked_at.is_none()));

        let revoked = store.revoke(PortalRevokeHandleRequest {
            handle_id: handle.handle_id,
            session_id: Some(session_id),
            user_id: Some("user-1".to_string()),
            reason: Some("user requested revocation".to_string()),
        })?;
        assert!(revoked
            .handle
            .as_ref()
            .is_some_and(|record| record.revoked_at.is_some()));

        let _ = std::fs::remove_dir_all(root);
        Ok(())
    }
}
