use std::{
    io::{Read, Write},
    net::Shutdown,
    os::unix::net::UnixStream,
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

use anyhow::Context;
use serde_json::Value;

use aios_contracts::{RuntimeInferRequest, RuntimeInferResponse};

use super::{BackendExecutionError, BackendFailureClass};

const WORKER_CONTRACT_V1: &str = "runtime-worker-v1";

pub struct WrapperExecution<'a> {
    pub backend_id: &'a str,
    pub request: &'a RuntimeInferRequest,
    pub estimated_latency_ms: u64,
    pub timeout_ms: u64,
    pub command: &'a str,
    pub default_route_state: &'a str,
}

pub struct ResponseEnvelope<'a> {
    pub backend_id: &'a str,
    pub estimated_latency_ms: u64,
    pub default_route_state: &'a str,
    pub expected_worker_contract: Option<&'a str>,
    pub require_worker_json: bool,
}

pub fn execute(spec: WrapperExecution<'_>) -> Result<RuntimeInferResponse, BackendExecutionError> {
    let payload = serde_json::json!({
        "backend_id": spec.backend_id,
        "session_id": spec.request.session_id,
        "task_id": spec.request.task_id,
        "prompt": spec.request.prompt,
        "model": spec.request.model,
        "estimated_latency_ms": spec.estimated_latency_ms,
        "timeout_ms": spec.timeout_ms,
    });
    let payload_bytes = serde_json::to_vec(&payload).unwrap_or_default();

    if let Some(socket_path) = spec.command.strip_prefix("unix://") {
        return execute_unix_worker(&payload_bytes, socket_path, &spec);
    }

    let mut child = Command::new("/bin/sh")
        .arg("-lc")
        .arg(spec.command)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| format!("failed to spawn backend wrapper for {}", spec.backend_id))
        .map_err(|error| {
            BackendExecutionError::new(
                BackendFailureClass::CommandFailed,
                "backend-wrapper-error",
                error.to_string(),
                fallback_for(spec.backend_id),
            )
        })?;

    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(payload_bytes.as_slice()).map_err(|error| {
            BackendExecutionError::new(
                BackendFailureClass::CommandFailed,
                "backend-wrapper-error",
                format!("failed to write request payload: {error}"),
                fallback_for(spec.backend_id),
            )
        })?;
    }

    let deadline = Instant::now() + Duration::from_millis(spec.timeout_ms.max(1));
    loop {
        match child.try_wait() {
            Ok(Some(_)) => break,
            Ok(None) => {
                if Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(BackendExecutionError::new(
                        BackendFailureClass::Timeout,
                        "backend-timeout",
                        format!(
                            "backend {} exceeded timeout budget of {}ms",
                            spec.backend_id, spec.timeout_ms
                        ),
                        fallback_for(spec.backend_id),
                    ));
                }
                thread::sleep(Duration::from_millis(10));
            }
            Err(error) => {
                return Err(BackendExecutionError::new(
                    BackendFailureClass::CommandFailed,
                    "backend-wrapper-error",
                    format!("failed to wait on backend wrapper: {error}"),
                    fallback_for(spec.backend_id),
                ));
            }
        }
    }

    let mut stdout = String::new();
    let mut stderr = String::new();
    if let Some(mut stream) = child.stdout.take() {
        let _ = stream.read_to_string(&mut stdout);
    }
    if let Some(mut stream) = child.stderr.take() {
        let _ = stream.read_to_string(&mut stderr);
    }

    let status = child.wait().map_err(|error| {
        BackendExecutionError::new(
            BackendFailureClass::CommandFailed,
            "backend-wrapper-error",
            format!("failed to finalize backend wrapper: {error}"),
            fallback_for(spec.backend_id),
        )
    })?;

    if !status.success() {
        return Err(BackendExecutionError::new(
            BackendFailureClass::CommandFailed,
            "backend-wrapper-error",
            format!(
                "backend {} exited with status {}: {}",
                spec.backend_id,
                status,
                stderr.trim()
            )
            .trim()
            .to_string(),
            fallback_for(spec.backend_id),
        ));
    }

    parse_response_body(
        stdout.trim(),
        ResponseEnvelope {
            backend_id: spec.backend_id,
            estimated_latency_ms: spec.estimated_latency_ms,
            default_route_state: spec.default_route_state,
            expected_worker_contract: None,
            require_worker_json: false,
        },
    )
}

fn execute_unix_worker(
    payload: &[u8],
    socket_path: &str,
    spec: &WrapperExecution<'_>,
) -> Result<RuntimeInferResponse, BackendExecutionError> {
    let timeout = Duration::from_millis(spec.timeout_ms.max(1));
    let mut stream = UnixStream::connect(socket_path).map_err(|error| {
        BackendExecutionError::new(
            BackendFailureClass::Unreachable,
            "backend-worker-unreachable",
            format!(
                "failed to connect to backend worker {} at {}: {}",
                spec.backend_id, socket_path, error
            ),
            fallback_for(spec.backend_id),
        )
    })?;

    stream
        .set_read_timeout(Some(timeout))
        .and_then(|_| stream.set_write_timeout(Some(timeout)))
        .map_err(|error| {
            BackendExecutionError::new(
                BackendFailureClass::CommandFailed,
                "backend-worker-error",
                format!(
                    "failed to apply timeout budget for backend worker {}: {}",
                    spec.backend_id, error
                ),
                fallback_for(spec.backend_id),
            )
        })?;

    stream.write_all(payload).map_err(|error| {
        classify_worker_io(spec.backend_id, "failed to write worker request", error)
    })?;
    let _ = stream.shutdown(Shutdown::Write);

    let mut body = String::new();
    stream.read_to_string(&mut body).map_err(|error| {
        classify_worker_io(spec.backend_id, "failed to read worker response", error)
    })?;

    parse_response_body(
        body.trim(),
        ResponseEnvelope {
            backend_id: spec.backend_id,
            estimated_latency_ms: spec.estimated_latency_ms,
            default_route_state: spec.default_route_state,
            expected_worker_contract: Some(WORKER_CONTRACT_V1),
            require_worker_json: true,
        },
    )
}

pub fn parse_response_body(
    body: &str,
    envelope: ResponseEnvelope<'_>,
) -> Result<RuntimeInferResponse, BackendExecutionError> {
    if body.trim().is_empty() {
        return Err(BackendExecutionError::new(
            BackendFailureClass::InvalidResponse,
            "backend-invalid-response",
            format!(
                "backend {} returned an empty response body",
                envelope.backend_id
            ),
            fallback_for(envelope.backend_id),
        ));
    }

    if let Ok(value) = serde_json::from_str::<Value>(body) {
        if let Some(expected_contract) = envelope.expected_worker_contract {
            let actual_contract = value
                .get("worker_contract")
                .and_then(Value::as_str)
                .unwrap_or_default();
            if actual_contract != expected_contract {
                return Err(BackendExecutionError::new(
                    BackendFailureClass::InvalidResponse,
                    "backend-invalid-response",
                    format!(
                        "backend {} worker contract mismatch: expected {}, got {}",
                        envelope.backend_id,
                        expected_contract,
                        if actual_contract.is_empty() {
                            "<missing>"
                        } else {
                            actual_contract
                        }
                    ),
                    fallback_for(envelope.backend_id),
                ));
            }

            let actual_backend = value
                .get("backend_id")
                .and_then(Value::as_str)
                .unwrap_or_default();
            if actual_backend != envelope.backend_id {
                return Err(BackendExecutionError::new(
                    BackendFailureClass::InvalidResponse,
                    "backend-invalid-response",
                    format!(
                        "backend {} worker backend mismatch: expected {}, got {}",
                        envelope.backend_id,
                        envelope.backend_id,
                        if actual_backend.is_empty() {
                            "<missing>"
                        } else {
                            actual_backend
                        }
                    ),
                    fallback_for(envelope.backend_id),
                ));
            }
        }

        let content = value
            .get("content")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        let route_state = value
            .get("route_state")
            .and_then(Value::as_str)
            .unwrap_or(envelope.default_route_state)
            .to_string();

        return Ok(RuntimeInferResponse {
            backend_id: envelope.backend_id.to_string(),
            route_state,
            content,
            degraded: value
                .get("degraded")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            rejected: value
                .get("rejected")
                .and_then(Value::as_bool)
                .unwrap_or(false),
            reason: value
                .get("reason")
                .and_then(Value::as_str)
                .map(ToOwned::to_owned),
            estimated_latency_ms: value
                .get("estimated_latency_ms")
                .and_then(Value::as_u64)
                .or(Some(envelope.estimated_latency_ms)),
            provider_id: None,
            runtime_service_id: None,
            provider_status: None,
            queue_saturated: None,
            runtime_budget: None,
            notes: Vec::new(),
        });
    }

    if envelope.require_worker_json {
        return Err(BackendExecutionError::new(
            BackendFailureClass::InvalidResponse,
            "backend-invalid-response",
            format!(
                "backend {} worker returned non-json response body",
                envelope.backend_id
            ),
            fallback_for(envelope.backend_id),
        ));
    }

    Ok(RuntimeInferResponse {
        backend_id: envelope.backend_id.to_string(),
        route_state: envelope.default_route_state.to_string(),
        content: body.to_string(),
        degraded: false,
        rejected: false,
        reason: Some("backend returned plain-text output".to_string()),
        estimated_latency_ms: Some(envelope.estimated_latency_ms),
        provider_id: None,
        runtime_service_id: None,
        provider_status: None,
        queue_saturated: None,
        runtime_budget: None,
        notes: Vec::new(),
    })
}

fn fallback_for(backend_id: &str) -> Option<&'static str> {
    if backend_id == "local-cpu" {
        None
    } else {
        Some("local-cpu")
    }
}

fn classify_worker_io(
    backend_id: &str,
    action: &str,
    error: std::io::Error,
) -> BackendExecutionError {
    let (class, route_state) = match error.kind() {
        std::io::ErrorKind::TimedOut | std::io::ErrorKind::WouldBlock => {
            (BackendFailureClass::Timeout, "backend-timeout")
        }
        std::io::ErrorKind::NotFound
        | std::io::ErrorKind::ConnectionRefused
        | std::io::ErrorKind::ConnectionReset
        | std::io::ErrorKind::BrokenPipe => (
            BackendFailureClass::Unreachable,
            "backend-worker-unreachable",
        ),
        _ => (BackendFailureClass::CommandFailed, "backend-worker-error"),
    };

    BackendExecutionError::new(
        class,
        route_state,
        format!("{action} for backend {backend_id}: {error}"),
        fallback_for(backend_id),
    )
}

#[cfg(test)]
mod tests {
    use std::{
        fs,
        os::unix::net::UnixListener,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use aios_contracts::RuntimeInferRequest;

    use super::*;

    fn request(task_id: &str) -> RuntimeInferRequest {
        RuntimeInferRequest {
            session_id: "session-1".to_string(),
            task_id: task_id.to_string(),
            prompt: "Summarize runtime state".to_string(),
            model: Some("smoke-model".to_string()),
            execution_token: None,
            preferred_backend: Some("local-gpu".to_string()),
        }
    }

    fn temp_socket_dir(name: &str) -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system time")
            .as_nanos();
        let root = if PathBuf::from("/tmp").exists() {
            PathBuf::from("/tmp")
        } else {
            std::env::temp_dir()
        };
        root.join(format!("aios-{name}-{suffix}"))
    }

    #[test]
    #[ignore = "requires local unix socket listener permissions not available in sandboxed unit-test environments"]
    fn execute_supports_unix_worker_commands() -> anyhow::Result<()> {
        let root = temp_socket_dir("unix-worker");
        fs::create_dir_all(&root)?;
        let socket_path = root.join("gpu.sock");
        let listener = UnixListener::bind(&socket_path)?;

        let server = thread::spawn(move || -> anyhow::Result<()> {
            let (mut stream, _) = listener.accept()?;
            let mut body = String::new();
            stream.read_to_string(&mut body)?;
            let request: serde_json::Value = serde_json::from_str(&body)?;
            assert_eq!(request["task_id"], "task-unix");
            stream.write_all(
                br#"{"worker_contract":"runtime-worker-v1","backend_id":"local-gpu","content":"gpu-unix-ok","route_state":"local-wrapper","reason":"unix worker"}"#,
            )?;
            Ok(())
        });

        let command = format!("unix://{}", socket_path.display());
        let response = execute(WrapperExecution {
            backend_id: "local-gpu",
            request: &request("task-unix"),
            estimated_latency_ms: 42,
            timeout_ms: 1_000,
            command: &command,
            default_route_state: "local-wrapper",
        })
        .expect("unix worker execution should succeed");

        assert_eq!(response.backend_id, "local-gpu");
        assert_eq!(response.route_state, "local-wrapper");
        assert_eq!(response.content, "gpu-unix-ok");
        assert_eq!(response.reason.as_deref(), Some("unix worker"));
        server
            .join()
            .expect("unix worker thread")
            .expect("unix worker result");

        let _ = fs::remove_dir_all(root);
        Ok(())
    }

    #[test]
    fn execute_reports_unreachable_when_unix_worker_socket_is_missing() {
        let command = "unix:///tmp/aios-runtimed-missing-worker.sock".to_string();
        let error = execute(WrapperExecution {
            backend_id: "local-gpu",
            request: &request("task-missing-unix"),
            estimated_latency_ms: 42,
            timeout_ms: 1_000,
            command: &command,
            default_route_state: "local-wrapper",
        })
        .expect_err("missing unix worker should fail");

        assert_eq!(error.class, BackendFailureClass::Unreachable);
        assert_eq!(error.route_state, "backend-worker-unreachable");
    }

    #[test]
    fn parse_response_body_rejects_worker_contract_mismatch() {
        let error = parse_response_body(
            r#"{"worker_contract":"runtime-worker-v0","backend_id":"local-gpu","content":"gpu-ok"}"#,
            ResponseEnvelope {
                backend_id: "local-gpu",
                estimated_latency_ms: 42,
                default_route_state: "local-wrapper",
                expected_worker_contract: Some(WORKER_CONTRACT_V1),
                require_worker_json: true,
            },
        )
        .expect_err("worker contract mismatch should fail");

        assert_eq!(error.class, BackendFailureClass::InvalidResponse);
        assert_eq!(error.route_state, "backend-invalid-response");
        assert!(error.reason.contains("worker contract mismatch"));
    }

    #[test]
    fn parse_response_body_rejects_worker_backend_mismatch() {
        let error = parse_response_body(
            r#"{"worker_contract":"runtime-worker-v1","backend_id":"local-npu","content":"gpu-ok"}"#,
            ResponseEnvelope {
                backend_id: "local-gpu",
                estimated_latency_ms: 42,
                default_route_state: "local-wrapper",
                expected_worker_contract: Some(WORKER_CONTRACT_V1),
                require_worker_json: true,
            },
        )
        .expect_err("worker backend mismatch should fail");

        assert_eq!(error.class, BackendFailureClass::InvalidResponse);
        assert_eq!(error.route_state, "backend-invalid-response");
        assert!(error.reason.contains("worker backend mismatch"));
    }
}
