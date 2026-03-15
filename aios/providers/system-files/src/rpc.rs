use std::sync::Arc;

use serde::{de::DeserializeOwned, Serialize};
use serde_json::Value;

use aios_contracts::{methods, ProviderFsBulkDeleteRequest, ProviderFsOpenRequest};
use aios_rpc::{RpcError, RpcResult, RpcRouter};

use crate::AppState;

pub fn build_router(state: AppState) -> Arc<RpcRouter> {
    let mut router = RpcRouter::new("system-files-provider");

    let health_state = state.clone();
    router.register_method(methods::SYSTEM_HEALTH_GET, move |_| {
        json(health_state.health())
    });

    let open_state = state.clone();
    router.register_method(methods::PROVIDER_FS_OPEN, move |params| {
        let request: ProviderFsOpenRequest = parse_params(params)?;
        let response = match crate::ops::open_target(&open_state, &request) {
            Ok(response) => response,
            Err(error) => {
                if let Err(audit_error) = open_state.audit_writer.append_error(
                    methods::PROVIDER_FS_OPEN,
                    Some(&request.execution_token),
                    Some(&request.handle_id),
                    &error.to_string(),
                ) {
                    tracing::warn!(?audit_error, "failed to append provider open audit error");
                }
                return Err(RpcError::Internal(error.to_string()));
            }
        };
        json(response)
    });

    let delete_state = state.clone();
    router.register_method(methods::SYSTEM_FILE_BULK_DELETE, move |params| {
        let request: ProviderFsBulkDeleteRequest = parse_params(params)?;
        let response = match crate::ops::bulk_delete(&delete_state, &request) {
            Ok(response) => response,
            Err(error) => {
                if let Err(audit_error) = delete_state.audit_writer.append_error(
                    methods::SYSTEM_FILE_BULK_DELETE,
                    Some(&request.execution_token),
                    Some(&request.handle_id),
                    &error.to_string(),
                ) {
                    tracing::warn!(?audit_error, "failed to append provider delete audit error");
                }
                return Err(RpcError::Internal(error.to_string()));
            }
        };
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
