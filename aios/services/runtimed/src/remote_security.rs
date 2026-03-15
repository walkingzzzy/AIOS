use std::path::Path;

use aios_contracts::{
    methods, ExecutionToken, RuntimeInferRequest, TokenVerifyRequest, TokenVerifyResponse,
};
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RemoteAuthorizationError {
    pub route_state: String,
    pub reason: String,
}

impl RemoteAuthorizationError {
    fn new(route_state: &str, reason: impl Into<String>) -> Self {
        Self {
            route_state: route_state.to_string(),
            reason: reason.into(),
        }
    }
}

pub fn authorize_attested_remote_request(
    policyd_socket: &Path,
    request: &RuntimeInferRequest,
    expected_target_hash: Option<&str>,
) -> Result<ExecutionToken, RemoteAuthorizationError> {
    let token = request.execution_token.clone().ok_or_else(|| {
        RemoteAuthorizationError::new(
            "remote-token-required",
            "attested-remote execution requires execution_token",
        )
    })?;

    ensure_request_context(&token, request, expected_target_hash)?;

    let verification =
        verify_token(policyd_socket, &token, expected_target_hash).map_err(|error| {
            RemoteAuthorizationError::new(
                "remote-policy-unavailable",
                format!("failed to verify attested-remote execution token: {error}"),
            )
        })?;

    if !verification.valid {
        return Err(RemoteAuthorizationError::new(
            "remote-token-invalid",
            format!(
                "attested-remote execution token rejected: {}",
                verification.reason
            ),
        ));
    }

    Ok(token)
}

pub fn attested_remote_target_hash(command: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(command.trim().as_bytes());
    format!("{:x}", hasher.finalize())
}

fn ensure_request_context(
    token: &ExecutionToken,
    request: &RuntimeInferRequest,
    expected_target_hash: Option<&str>,
) -> Result<(), RemoteAuthorizationError> {
    if token.capability_id != methods::RUNTIME_INFER_SUBMIT {
        return Err(RemoteAuthorizationError::new(
            "remote-token-invalid",
            format!(
                "execution token capability {} does not match {}",
                token.capability_id,
                methods::RUNTIME_INFER_SUBMIT
            ),
        ));
    }
    if token.execution_location != "attested_remote" {
        return Err(RemoteAuthorizationError::new(
            "remote-token-invalid",
            format!(
                "execution token execution_location {} does not allow attested-remote",
                token.execution_location
            ),
        ));
    }
    if token.session_id != request.session_id {
        return Err(RemoteAuthorizationError::new(
            "remote-token-invalid",
            format!(
                "request session_id {} does not match token session_id {}",
                request.session_id, token.session_id
            ),
        ));
    }
    if token.task_id != request.task_id {
        return Err(RemoteAuthorizationError::new(
            "remote-token-invalid",
            format!(
                "request task_id {} does not match token task_id {}",
                request.task_id, token.task_id
            ),
        ));
    }
    if let Some(expected_target_hash) = expected_target_hash {
        if token.target_hash.as_deref() != Some(expected_target_hash) {
            return Err(RemoteAuthorizationError::new(
                "remote-token-invalid",
                "execution token target_hash does not match configured attested-remote target",
            ));
        }
    }

    Ok(())
}

fn verify_token(
    policyd_socket: &Path,
    token: &ExecutionToken,
    expected_target_hash: Option<&str>,
) -> anyhow::Result<TokenVerifyResponse> {
    aios_rpc::call_unix(
        policyd_socket,
        methods::POLICY_TOKEN_VERIFY,
        &TokenVerifyRequest {
            token: token.clone(),
            target_hash: expected_target_hash.map(str::to_string),
            consume: false,
        },
    )
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;

    fn request() -> RuntimeInferRequest {
        RuntimeInferRequest {
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            prompt: "route to attested remote".to_string(),
            model: Some("smoke-model".to_string()),
            execution_token: None,
            preferred_backend: Some("attested-remote".to_string()),
        }
    }

    fn token(execution_location: &str) -> ExecutionToken {
        ExecutionToken {
            user_id: "user-1".to_string(),
            session_id: "session-1".to_string(),
            task_id: "task-1".to_string(),
            capability_id: methods::RUNTIME_INFER_SUBMIT.to_string(),
            target_hash: None,
            expiry: "2099-01-01T00:00:00Z".to_string(),
            approval_ref: None,
            constraints: BTreeMap::new(),
            execution_location: execution_location.to_string(),
            taint_summary: None,
            signature: Some("sig".to_string()),
        }
    }

    #[test]
    fn authorize_rejects_missing_token() {
        let error = authorize_attested_remote_request(
            Path::new("/tmp/missing.sock"),
            &request(),
            Some("expected-target-hash"),
        )
        .expect_err("missing token should be rejected");
        assert_eq!(error.route_state, "remote-token-required");
    }

    #[test]
    fn authorize_rejects_non_remote_execution_location() {
        let mut request = request();
        request.execution_token = Some(token("local"));

        let error = authorize_attested_remote_request(
            Path::new("/tmp/missing.sock"),
            &request,
            Some("expected-target-hash"),
        )
        .expect_err("local token should be rejected");
        assert_eq!(error.route_state, "remote-token-invalid");
        assert!(error.reason.contains("execution_location"));
    }

    #[test]
    fn authorize_rejects_mismatched_target_hash_before_policy_call() {
        let expected_target_hash = attested_remote_target_hash(" http://127.0.0.1:8080/infer ");
        let mut request = request();
        let mut execution_token = token("attested_remote");
        execution_token.target_hash = Some("different-target".to_string());
        request.execution_token = Some(execution_token);

        let error = authorize_attested_remote_request(
            Path::new("/tmp/missing.sock"),
            &request,
            Some(expected_target_hash.as_str()),
        )
        .expect_err("mismatched target hash should be rejected");

        assert_eq!(error.route_state, "remote-token-invalid");
        assert!(error.reason.contains("target_hash"));
    }

    #[test]
    fn attested_remote_target_hash_trims_command_whitespace() {
        let baseline = attested_remote_target_hash("http://127.0.0.1:8080/infer");
        let padded = attested_remote_target_hash("  http://127.0.0.1:8080/infer  ");

        assert_eq!(baseline, padded);
    }
}
