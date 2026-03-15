use std::{
    cell::RefCell,
    sync::{Once, OnceLock},
};

use serde::{Deserialize, Serialize};
use tracing_subscriber::{fmt::format::FmtSpan, EnvFilter};
use uuid::Uuid;

static LOGGING_INIT: Once = Once::new();
static SERVICE_NAME: OnceLock<String> = OnceLock::new();

thread_local! {
    static TRACE_CONTEXT_STACK: RefCell<Vec<TraceContext>> = const { RefCell::new(Vec::new()) };
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TraceContext {
    pub trace_id: String,
    pub span_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent_span_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub origin_service: Option<String>,
}

impl TraceContext {
    pub fn root(origin_service: Option<&str>) -> Self {
        Self {
            trace_id: new_trace_id(),
            span_id: new_span_id(),
            parent_span_id: None,
            origin_service: origin_service.map(str::to_string),
        }
    }

    pub fn child_of(parent: Option<&TraceContext>, origin_service: Option<&str>) -> Self {
        match parent {
            Some(parent) => Self {
                trace_id: parent.trace_id.clone(),
                span_id: new_span_id(),
                parent_span_id: Some(parent.span_id.clone()),
                origin_service: origin_service.map(str::to_string),
            },
            None => Self::root(origin_service),
        }
    }
}

pub fn init(service_name: &str) {
    let _ = SERVICE_NAME.set(service_name.to_string());

    LOGGING_INIT.call_once(|| {
        let env_filter =
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info"));

        tracing_subscriber::fmt()
            .with_env_filter(env_filter)
            .with_target(false)
            .with_thread_names(true)
            .with_span_events(FmtSpan::NEW | FmtSpan::CLOSE)
            .compact()
            .init();
    });
}

pub fn service_name() -> Option<&'static str> {
    SERVICE_NAME.get().map(String::as_str)
}

pub fn current_trace_context() -> Option<TraceContext> {
    TRACE_CONTEXT_STACK.with(|stack| stack.borrow().last().cloned())
}

pub fn outbound_trace_context() -> TraceContext {
    TraceContext::child_of(current_trace_context().as_ref(), service_name())
}

pub fn inbound_trace_context(parent: Option<&TraceContext>) -> TraceContext {
    TraceContext::child_of(parent, service_name())
}

pub fn with_trace_context<T>(context: TraceContext, operation: impl FnOnce() -> T) -> T {
    struct TraceScopeGuard;

    impl Drop for TraceScopeGuard {
        fn drop(&mut self) {
            TRACE_CONTEXT_STACK.with(|stack| {
                stack.borrow_mut().pop();
            });
        }
    }

    TRACE_CONTEXT_STACK.with(|stack| {
        stack.borrow_mut().push(context);
    });

    let _guard = TraceScopeGuard;
    operation()
}

fn new_trace_id() -> String {
    format!("trc-{}", Uuid::new_v4().simple())
}

fn new_span_id() -> String {
    format!("spn-{}", Uuid::new_v4().simple())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn outbound_context_inherits_active_trace() {
        let root = TraceContext::root(Some("root-service"));

        with_trace_context(root.clone(), || {
            let child = outbound_trace_context();
            assert_eq!(child.trace_id, root.trace_id);
            assert_eq!(child.parent_span_id.as_deref(), Some(root.span_id.as_str()));
            assert_eq!(child.origin_service.as_deref(), service_name());
        });
    }

    #[test]
    fn inbound_context_reuses_incoming_trace_id() {
        let incoming = TraceContext::root(Some("agentd"));
        let child = inbound_trace_context(Some(&incoming));

        assert_eq!(child.trace_id, incoming.trace_id);
        assert_eq!(
            child.parent_span_id.as_deref(),
            Some(incoming.span_id.as_str())
        );
    }
}
