use std::sync::Arc;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::Value;

use aios_contracts::{methods, SystemIntentRequest};
use aios_rpc::{RpcError, RpcResult, RpcRouter};

use crate::AppState;

pub fn build_router(state: AppState) -> Arc<RpcRouter> {
    let mut router = RpcRouter::new("system-intent-provider");

    let health_state = state.clone();
    router.register_method(methods::SYSTEM_HEALTH_GET, move |_| {
        json(health_state.health())
    });

    let execute_state = state.clone();
    router.register_method(methods::SYSTEM_INTENT_EXECUTE, move |params| {
        let request: SystemIntentRequest = parse_params(params)?;
        let response = crate::ops::execute_intent(&execute_state, &request)
            .map_err(|error| RpcError::Internal(error.to_string()))?;
        json(response)
    });

    Arc::new(router)
}

fn parse_params<T>(params: Option<Value>) -> Result<T, RpcError>
where
    T: DeserializeOwned,
{
    serde_json::from_value(params.unwrap_or(Value::Null))
        .map_err(|error| RpcError::InvalidParams(error.to_string()))
}

fn json<T>(value: T) -> RpcResult
where
    T: Serialize,
{
    serde_json::to_value(value).map_err(|error| RpcError::Internal(error.to_string()))
}
