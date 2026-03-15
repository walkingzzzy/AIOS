use std::{
    io::{Read, Write},
    net::{TcpStream, ToSocketAddrs},
    time::Duration,
};

use aios_contracts::{RuntimeInferRequest, RuntimeInferResponse};

use super::{
    capability::{env_truthy, BackendReadiness},
    wrapper, BackendExecutionError, BackendFailureClass, RuntimeBackend,
};

#[derive(Debug, Clone, Copy)]
pub struct AttestedRemoteBackend;

#[derive(Debug)]
struct HttpTarget {
    authority: String,
    host: String,
    port: u16,
    path: String,
}

impl RuntimeBackend for AttestedRemoteBackend {
    fn backend_id(&self) -> &'static str {
        "attested-remote"
    }

    fn readiness(&self, command: Option<&str>) -> BackendReadiness {
        if env_truthy("AIOS_RUNTIMED_DISABLE_ATTESTED_REMOTE") {
            return BackendReadiness::unavailable(
                "disabled",
                "runtime-config",
                "attested-remote backend disabled by environment",
            );
        }

        match command {
            Some(endpoint) if endpoint.starts_with("http://") => BackendReadiness::available(
                "configured-remote-endpoint",
                "attested-remote endpoint configured",
            ),
            Some(_) => BackendReadiness::available(
                "configured-wrapper",
                "attested-remote wrapper configured",
            ),
            None => BackendReadiness::unavailable(
                "disabled",
                "policy-approval+attestation+configured-endpoint",
                "attested-remote endpoint not configured",
            ),
        }
    }

    fn execute(
        &self,
        request: &RuntimeInferRequest,
        estimated_latency_ms: u64,
        timeout_ms: u64,
        command: Option<&str>,
    ) -> Result<RuntimeInferResponse, BackendExecutionError> {
        let readiness = self.readiness(command);
        let Some(command) = command else {
            return Err(BackendExecutionError::new(
                BackendFailureClass::Unavailable,
                "remote-disabled",
                readiness.reason,
                Some("local-cpu"),
            ));
        };

        if command.starts_with("http://") {
            return execute_http_remote(request, estimated_latency_ms, timeout_ms, command);
        }

        wrapper::execute(wrapper::WrapperExecution {
            backend_id: self.backend_id(),
            request,
            estimated_latency_ms,
            timeout_ms,
            command,
            default_route_state: "attested-remote-wrapper",
        })
    }
}

fn execute_http_remote(
    request: &RuntimeInferRequest,
    estimated_latency_ms: u64,
    timeout_ms: u64,
    endpoint: &str,
) -> Result<RuntimeInferResponse, BackendExecutionError> {
    let target = parse_http_target(endpoint)?;
    let timeout = Duration::from_millis(timeout_ms.max(1));
    let addr = (target.host.as_str(), target.port)
        .to_socket_addrs()
        .map_err(|error| {
            BackendExecutionError::new(
                BackendFailureClass::Unreachable,
                "remote-unreachable",
                format!("failed to resolve remote endpoint {}: {error}", endpoint),
                Some("local-cpu"),
            )
        })?
        .next()
        .ok_or_else(|| {
            BackendExecutionError::new(
                BackendFailureClass::Unreachable,
                "remote-unreachable",
                format!("no socket address resolved for {}", endpoint),
                Some("local-cpu"),
            )
        })?;

    let mut stream = TcpStream::connect_timeout(&addr, timeout).map_err(|error| {
        BackendExecutionError::new(
            BackendFailureClass::Unreachable,
            "remote-unreachable",
            format!("failed to connect to remote endpoint {}: {error}", endpoint),
            Some("local-cpu"),
        )
    })?;
    stream
        .set_read_timeout(Some(timeout))
        .and_then(|_| stream.set_write_timeout(Some(timeout)))
        .map_err(|error| {
            BackendExecutionError::new(
                BackendFailureClass::Timeout,
                "backend-timeout",
                format!("failed to apply remote timeout budget: {error}"),
                Some("local-cpu"),
            )
        })?;

    let payload = serde_json::json!({
        "backend_id": "attested-remote",
        "session_id": request.session_id,
        "task_id": request.task_id,
        "prompt": request.prompt,
        "model": request.model,
        "estimated_latency_ms": estimated_latency_ms,
        "timeout_ms": timeout_ms,
    });
    let body = serde_json::to_string(&payload).map_err(|error| {
        BackendExecutionError::new(
            BackendFailureClass::InvalidResponse,
            "backend-invalid-response",
            format!("failed to serialize remote payload: {error}"),
            Some("local-cpu"),
        )
    })?;
    let request_text = format!(
        "POST {} HTTP/1.1\r\nHost: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        target.path,
        target.authority,
        body.len(),
        body
    );

    stream.write_all(request_text.as_bytes()).map_err(|error| {
        classify_remote_io_error("failed to write remote request", error, Some("local-cpu"))
    })?;

    let mut response_text = String::new();
    stream.read_to_string(&mut response_text).map_err(|error| {
        classify_remote_io_error("failed to read remote response", error, Some("local-cpu"))
    })?;

    let (status_code, response_body) = parse_http_response(&response_text)?;
    if status_code != 200 {
        return Err(BackendExecutionError::new(
            BackendFailureClass::Unreachable,
            "remote-error",
            format!(
                "remote endpoint returned HTTP {} with body: {}",
                status_code,
                response_body.trim()
            ),
            Some("local-cpu"),
        ));
    }

    wrapper::parse_response_body(
        response_body.trim(),
        wrapper::ResponseEnvelope {
            backend_id: "attested-remote",
            estimated_latency_ms,
            default_route_state: "attested-remote",
            expected_worker_contract: None,
            require_worker_json: false,
        },
    )
}

fn parse_http_target(endpoint: &str) -> Result<HttpTarget, BackendExecutionError> {
    let rest = endpoint.strip_prefix("http://").ok_or_else(|| {
        BackendExecutionError::new(
            BackendFailureClass::Unavailable,
            "remote-invalid-config",
            format!("unsupported remote endpoint scheme for {}", endpoint),
            Some("local-cpu"),
        )
    })?;

    let (authority, path) = match rest.split_once('/') {
        Some((authority, path)) => (authority, format!("/{}", path)),
        None => (rest, "/".to_string()),
    };
    let (host, port) = match authority.rsplit_once(':') {
        Some((host, port)) => {
            let port = port.parse::<u16>().map_err(|_| {
                BackendExecutionError::new(
                    BackendFailureClass::Unavailable,
                    "remote-invalid-config",
                    format!("invalid remote endpoint port in {}", endpoint),
                    Some("local-cpu"),
                )
            })?;
            (host.to_string(), port)
        }
        None => (authority.to_string(), 80),
    };

    Ok(HttpTarget {
        authority: authority.to_string(),
        host,
        port,
        path,
    })
}

fn parse_http_response(response: &str) -> Result<(u16, &str), BackendExecutionError> {
    let (headers, body) = response.split_once("\r\n\r\n").ok_or_else(|| {
        BackendExecutionError::new(
            BackendFailureClass::InvalidResponse,
            "backend-invalid-response",
            "remote endpoint returned malformed HTTP response",
            Some("local-cpu"),
        )
    })?;
    let status_line = headers.lines().next().ok_or_else(|| {
        BackendExecutionError::new(
            BackendFailureClass::InvalidResponse,
            "backend-invalid-response",
            "remote endpoint returned empty HTTP status line",
            Some("local-cpu"),
        )
    })?;
    let status_code = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| {
            BackendExecutionError::new(
                BackendFailureClass::InvalidResponse,
                "backend-invalid-response",
                format!("unable to parse remote HTTP status line: {}", status_line),
                Some("local-cpu"),
            )
        })?;

    Ok((status_code, body))
}

fn classify_remote_io_error(
    prefix: &str,
    error: std::io::Error,
    fallback_backend: Option<&'static str>,
) -> BackendExecutionError {
    use std::io::ErrorKind;

    let class = match error.kind() {
        ErrorKind::TimedOut | ErrorKind::WouldBlock => BackendFailureClass::Timeout,
        _ => BackendFailureClass::Unreachable,
    };
    let route_state = match class {
        BackendFailureClass::Timeout => "backend-timeout",
        _ => "remote-unreachable",
    };

    BackendExecutionError::new(
        class,
        route_state,
        format!("{prefix}: {error}"),
        fallback_backend,
    )
}
