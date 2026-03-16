use std::{collections::HashMap, path::Path, sync::Arc, time::Duration};

#[cfg(unix)]
use std::{
    io::{BufRead, BufReader as StdBufReader, Write},
    os::unix::net::UnixStream as BlockingUnixStream,
};

#[cfg(unix)]
use aios_core::logging as core_logging;
use aios_core::logging::TraceContext;
#[cfg(unix)]
use anyhow::Context;
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

#[cfg(unix)]
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{UnixListener, UnixStream},
};

pub type RpcResult = Result<Value, RpcError>;

type BoxedHandler = Arc<dyn Fn(Option<Value>) -> RpcResult + Send + Sync>;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum RpcId {
    Number(i64),
    String(String),
    Null,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RpcRequest {
    pub jsonrpc: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub id: Option<RpcId>,
    pub method: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub params: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub trace_context: Option<TraceContext>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RpcErrorObject {
    pub code: i32,
    pub message: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub data: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RpcResponse {
    pub jsonrpc: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub id: Option<RpcId>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error: Option<RpcErrorObject>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub trace_context: Option<TraceContext>,
}

impl RpcResponse {
    pub fn success(id: Option<RpcId>, result: Value) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            id,
            result: Some(result),
            error: None,
            trace_context: None,
        }
    }

    pub fn error(id: Option<RpcId>, error: RpcErrorObject) -> Self {
        Self {
            jsonrpc: "2.0".to_string(),
            id,
            result: None,
            error: Some(error),
            trace_context: None,
        }
    }
}

#[derive(Debug, Error)]
pub enum RpcError {
    #[error("invalid request: {0}")]
    InvalidRequest(String),
    #[error("method not found: {0}")]
    MethodNotFound(String),
    #[error("invalid params: {0}")]
    InvalidParams(String),
    #[error("internal error: {0}")]
    Internal(String),
    #[error("{resource} not found: {identifier}")]
    ResourceNotFound {
        resource: String,
        identifier: String,
    },
    #[error("conflict: {message}")]
    Conflict { error_code: String, message: String },
    #[error("precondition failed: {message}")]
    PreconditionFailed { error_code: String, message: String },
    #[error("permission denied: {message}")]
    PermissionDenied { error_code: String, message: String },
    #[error("service unavailable: {message}")]
    Unavailable { error_code: String, message: String },
    #[error("timeout: {message}")]
    Timeout { error_code: String, message: String },
    #[error("invalid params: {message}")]
    InvalidParamsCode {
        error_code: String,
        message: String,
        #[source]
        source: Option<anyhow::Error>,
    },
    #[error("internal error: {message}")]
    InternalCode {
        error_code: String,
        message: String,
        #[source]
        source: Option<anyhow::Error>,
    },
}

impl RpcError {
    pub fn resource_not_found(resource: impl Into<String>, identifier: impl Into<String>) -> Self {
        Self::ResourceNotFound {
            resource: resource.into(),
            identifier: identifier.into(),
        }
    }

    pub fn conflict(error_code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::Conflict {
            error_code: error_code.into(),
            message: message.into(),
        }
    }

    pub fn precondition_failed(error_code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::PreconditionFailed {
            error_code: error_code.into(),
            message: message.into(),
        }
    }

    pub fn permission_denied(error_code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::PermissionDenied {
            error_code: error_code.into(),
            message: message.into(),
        }
    }

    pub fn unavailable(error_code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::Unavailable {
            error_code: error_code.into(),
            message: message.into(),
        }
    }

    pub fn timeout(error_code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::Timeout {
            error_code: error_code.into(),
            message: message.into(),
        }
    }

    pub fn invalid_params_code(error_code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::InvalidParamsCode {
            error_code: error_code.into(),
            message: message.into(),
            source: None,
        }
    }

    pub fn internal_code(error_code: impl Into<String>, message: impl Into<String>) -> Self {
        Self::InternalCode {
            error_code: error_code.into(),
            message: message.into(),
            source: None,
        }
    }

    pub fn to_object(&self) -> RpcErrorObject {
        let (code, error_code, data) = match self {
            Self::InvalidRequest(_) => (-32600, "invalid_request".to_string(), None),
            Self::MethodNotFound(_) => (-32601, "method_not_found".to_string(), None),
            Self::InvalidParams(_) => (-32602, "invalid_params".to_string(), None),
            Self::Internal(_) => (-32603, "internal_error".to_string(), None),
            Self::ResourceNotFound {
                resource,
                identifier,
            } => (
                -32001,
                "resource_not_found".to_string(),
                Some(serde_json::json!({
                    "resource": resource,
                    "identifier": identifier,
                })),
            ),
            Self::Conflict { error_code, .. } => (-32002, error_code.clone(), None),
            Self::PreconditionFailed { error_code, .. } => (-32003, error_code.clone(), None),
            Self::PermissionDenied { error_code, .. } => (-32004, error_code.clone(), None),
            Self::Unavailable { error_code, .. } => (-32005, error_code.clone(), None),
            Self::Timeout { error_code, .. } => (-32006, error_code.clone(), None),
            Self::InvalidParamsCode { error_code, .. } => (-32602, error_code.clone(), None),
            Self::InternalCode { error_code, .. } => (-32603, error_code.clone(), None),
        };

        let data = merge_error_data(error_code, data);

        RpcErrorObject {
            code,
            message: self.to_string(),
            data,
        }
    }
}

fn merge_error_data(error_code: String, data: Option<Value>) -> Option<Value> {
    let mut object = serde_json::Map::new();
    object.insert("error_code".to_string(), Value::String(error_code));
    if let Some(data) = data {
        match data {
            Value::Object(map) => {
                object.extend(map);
            }
            other => {
                object.insert("details".to_string(), other);
            }
        }
    }
    Some(Value::Object(object))
}

#[derive(Default)]
pub struct RpcRouter {
    service_name: String,
    methods: HashMap<String, BoxedHandler>,
}

impl std::fmt::Debug for RpcRouter {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let mut method_names = self.methods.keys().cloned().collect::<Vec<_>>();
        method_names.sort();
        f.debug_struct("RpcRouter")
            .field("service_name", &self.service_name)
            .field("method_names", &method_names)
            .finish()
    }
}

impl RpcRouter {
    pub fn new(service_name: impl Into<String>) -> Self {
        Self {
            service_name: service_name.into(),
            methods: HashMap::new(),
        }
    }

    pub fn register_method<F>(&mut self, name: impl Into<String>, handler: F)
    where
        F: Fn(Option<Value>) -> RpcResult + Send + Sync + 'static,
    {
        self.methods.insert(name.into(), Arc::new(handler));
    }

    pub fn handle(&self, request: RpcRequest) -> RpcResponse {
        if request.jsonrpc != "2.0" {
            return RpcResponse::error(
                request.id,
                RpcError::InvalidRequest("jsonrpc field must be 2.0".to_string()).to_object(),
            );
        }

        let Some(handler) = self.methods.get(&request.method) else {
            return RpcResponse::error(
                request.id,
                RpcError::MethodNotFound(request.method).to_object(),
            );
        };

        match handler(request.params) {
            Ok(result) => RpcResponse::success(request.id, result),
            Err(error) => RpcResponse::error(request.id, error.to_object()),
        }
    }

    pub fn service_name(&self) -> &str {
        &self.service_name
    }
}

#[cfg(unix)]
pub async fn serve_unix<P>(socket_path: P, router: Arc<RpcRouter>) -> anyhow::Result<()>
where
    P: AsRef<Path>,
{
    let socket_path = socket_path.as_ref().to_path_buf();

    if let Some(parent) = socket_path.parent() {
        tokio::fs::create_dir_all(parent)
            .await
            .with_context(|| format!("failed to create socket parent {}", parent.display()))?;
    }

    if socket_path.exists() {
        std::fs::remove_file(&socket_path).with_context(|| {
            format!(
                "failed to remove stale rpc socket {}",
                socket_path.display()
            )
        })?;
    }

    let listener = UnixListener::bind(&socket_path)
        .with_context(|| format!("failed to bind rpc socket {}", socket_path.display()))?;
    tracing::info!(service = router.service_name(), socket = %socket_path.display(), "rpc socket ready");

    loop {
        let (stream, _) = listener.accept().await?;
        let router = Arc::clone(&router);

        tokio::spawn(async move {
            if let Err(error) = handle_connection(stream, router).await {
                tracing::warn!(?error, "rpc connection closed with error");
            }
        });
    }
}

#[cfg(not(unix))]
pub async fn serve_unix<P>(socket_path: P, _router: Arc<RpcRouter>) -> anyhow::Result<()>
where
    P: AsRef<Path>,
{
    Err(unix_rpc_unsupported(socket_path.as_ref()))
}

pub fn call_unix<Request, Response, P>(
    socket_path: P,
    method: &str,
    params: &Request,
) -> anyhow::Result<Response>
where
    Request: Serialize,
    Response: DeserializeOwned,
    P: AsRef<Path>,
{
    call_unix_with_timeout(socket_path, method, params, Duration::from_secs(5))
}

#[cfg(unix)]
pub fn call_unix_with_timeout<Request, Response, P>(
    socket_path: P,
    method: &str,
    params: &Request,
    timeout: Duration,
) -> anyhow::Result<Response>
where
    Request: Serialize,
    Response: DeserializeOwned,
    P: AsRef<Path>,
{
    let trace_context = core_logging::outbound_trace_context();
    log_trace_event(
        core_logging::service_name().unwrap_or("rpc-client"),
        "rpc.request.send",
        method,
        socket_path.as_ref(),
        &trace_context,
        None,
    );

    let request = RpcRequest {
        jsonrpc: "2.0".to_string(),
        id: Some(RpcId::Number(1)),
        method: method.to_string(),
        params: Some(serde_json::to_value(params)?),
        trace_context: Some(trace_context.clone()),
    };

    let mut stream = BlockingUnixStream::connect(socket_path.as_ref())
        .with_context(|| format!("failed to connect to {}", socket_path.as_ref().display()))?;
    stream.set_read_timeout(Some(timeout))?;
    stream.set_write_timeout(Some(timeout))?;

    stream.write_all(serde_json::to_string(&request)?.as_bytes())?;
    stream.write_all(
        b"
",
    )?;
    stream.flush()?;

    let mut response_line = String::new();
    StdBufReader::new(stream).read_line(&mut response_line)?;
    let response: RpcResponse = serde_json::from_str(&response_line)?;

    if let Some(server_trace_context) = response.trace_context.as_ref() {
        log_trace_event(
            core_logging::service_name().unwrap_or("rpc-client"),
            "rpc.response.recv",
            method,
            socket_path.as_ref(),
            server_trace_context,
            Some(if response.error.is_some() {
                "error"
            } else {
                "ok"
            }),
        );
    }

    if let Some(error) = response.error {
        let error_code = error
            .data
            .as_ref()
            .and_then(|value| value.get("error_code"))
            .and_then(Value::as_str);
        if let Some(error_code) = error_code {
            anyhow::bail!(
                "remote rpc error {} [{}]: {}",
                error.code,
                error_code,
                error.message
            );
        }
        anyhow::bail!("remote rpc error {}: {}", error.code, error.message);
    }

    let result = response.result.context("rpc response missing result")?;
    Ok(serde_json::from_value(result)?)
}

#[cfg(not(unix))]
pub fn call_unix_with_timeout<Request, Response, P>(
    socket_path: P,
    _method: &str,
    _params: &Request,
    _timeout: Duration,
) -> anyhow::Result<Response>
where
    Request: Serialize,
    Response: DeserializeOwned,
    P: AsRef<Path>,
{
    Err(unix_rpc_unsupported(socket_path.as_ref()))
}

#[cfg(not(unix))]
fn unix_rpc_unsupported(socket_path: &Path) -> anyhow::Error {
    anyhow::anyhow!(
        "unix rpc transport is not supported on this platform: {}",
        socket_path.display()
    )
}

#[cfg(unix)]
fn log_trace_event(
    service: &str,
    event: &str,
    method: &str,
    socket_path: &Path,
    trace_context: &TraceContext,
    status: Option<&str>,
) {
    tracing::info!(
        service,
        event,
        method,
        socket = %socket_path.display(),
        trace_id = %trace_context.trace_id,
        span_id = %trace_context.span_id,
        parent_span_id = trace_context.parent_span_id.as_deref().unwrap_or("-"),
        origin_service = trace_context.origin_service.as_deref().unwrap_or("-"),
        status = status.unwrap_or("-"),
        "rpc trace"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn structured_not_found_error_exposes_shared_error_code() {
        let error = RpcError::resource_not_found("session", "session-1").to_object();
        assert_eq!(error.code, -32001);
        assert_eq!(
            error
                .data
                .as_ref()
                .and_then(|value| value.get("error_code"))
                .and_then(Value::as_str),
            Some("resource_not_found")
        );
        assert_eq!(
            error
                .data
                .as_ref()
                .and_then(|value| value.get("resource"))
                .and_then(Value::as_str),
            Some("session")
        );
    }

    #[test]
    fn invalid_params_code_uses_standard_json_rpc_code_with_shared_error_code() {
        let error =
            RpcError::invalid_params_code("intent_empty", "intent cannot be empty").to_object();
        assert_eq!(error.code, -32602);
        assert_eq!(
            error
                .data
                .as_ref()
                .and_then(|value| value.get("error_code"))
                .and_then(Value::as_str),
            Some("intent_empty")
        );
    }
}

#[cfg(unix)]
async fn handle_connection(stream: UnixStream, router: Arc<RpcRouter>) -> anyhow::Result<()> {
    let (reader, mut writer) = stream.into_split();
    let mut lines = BufReader::new(reader).lines();

    while let Some(line) = lines.next_line().await? {
        if line.trim().is_empty() {
            continue;
        }

        let response = match serde_json::from_str::<RpcRequest>(&line) {
            Ok(request) => {
                let router = Arc::clone(&router);
                tokio::task::spawn_blocking(move || {
                    let method = request.method.clone();
                    let trace_context =
                        core_logging::inbound_trace_context(request.trace_context.as_ref());

                    core_logging::with_trace_context(trace_context.clone(), || {
                        tracing::info!(
                            service = router.service_name(),
                            event = "rpc.request.recv",
                            method,
                            trace_id = %trace_context.trace_id,
                            span_id = %trace_context.span_id,
                            parent_span_id = trace_context.parent_span_id.as_deref().unwrap_or("-"),
                            origin_service = trace_context.origin_service.as_deref().unwrap_or("-"),
                            "rpc trace"
                        );

                        let mut response = router.handle(request);
                        response.trace_context = Some(trace_context.clone());

                        tracing::info!(
                            service = router.service_name(),
                            event = "rpc.response.send",
                            method,
                            trace_id = %trace_context.trace_id,
                            span_id = %trace_context.span_id,
                            parent_span_id = trace_context.parent_span_id.as_deref().unwrap_or("-"),
                            origin_service = trace_context.origin_service.as_deref().unwrap_or("-"),
                            status = if response.error.is_some() { "error" } else { "ok" },
                            "rpc trace"
                        );

                        response
                    })
                })
                .await
                .map_err(|error| anyhow::anyhow!("rpc handler task failed: {error}"))?
            }
            Err(error) => RpcResponse::error(
                None,
                RpcError::InvalidRequest(error.to_string()).to_object(),
            ),
        };

        writer
            .write_all(serde_json::to_string(&response)?.as_bytes())
            .await?;
        writer.write_all(b"\n").await?;
    }

    Ok(())
}
