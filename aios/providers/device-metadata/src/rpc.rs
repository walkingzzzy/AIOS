use std::sync::Arc;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::Value;

use aios_contracts::{methods, DeviceMetadataGetRequest};
use aios_rpc::{RpcError, RpcResult, RpcRouter};

use crate::AppState;

pub fn build_router(state: AppState) -> Arc<RpcRouter> {
    let mut router = RpcRouter::new("device-metadata-provider");

    let health_state = state.clone();
    router.register_method(methods::SYSTEM_HEALTH_GET, move |_| {
        json(health_state.health())
    });

    let metadata_state = state.clone();
    router.register_method(methods::DEVICE_METADATA_GET, move |params| {
        let request: DeviceMetadataGetRequest = parse_params(params)?;
        let response = crate::ops::get_device_metadata(&metadata_state, &request);
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
