/**
 * JSON-RPC 2.0 类型定义
 */

/** JSON-RPC 请求 */
export interface JSONRPCRequest {
    jsonrpc: '2.0';
    id: string | number | null;
    method: string;
    params?: Record<string, unknown> | unknown[];
}

/** JSON-RPC 成功响应 */
export interface JSONRPCSuccessResponse {
    jsonrpc: '2.0';
    id: string | number | null;
    result: unknown;
}

/** JSON-RPC 错误对象 */
export interface JSONRPCError {
    code: number;
    message: string;
    data?: unknown;
}

/** JSON-RPC 错误响应 */
export interface JSONRPCErrorResponse {
    jsonrpc: '2.0';
    id: string | number | null;
    error: JSONRPCError;
}

/** JSON-RPC 响应 */
export type JSONRPCResponse = JSONRPCSuccessResponse | JSONRPCErrorResponse;

/** 标准 JSON-RPC 错误码 */
export const JSONRPCErrorCodes = {
    PARSE_ERROR: -32700,
    INVALID_REQUEST: -32600,
    METHOD_NOT_FOUND: -32601,
    INVALID_PARAMS: -32602,
    INTERNAL_ERROR: -32603,
    // AIOS 自定义错误码
    ADAPTER_NOT_FOUND: -32001,
    CAPABILITY_NOT_FOUND: -32002,
    PERMISSION_DENIED: -32003,
    OPERATION_FAILED: -32004,
} as const;

/** 创建成功响应 */
export function createSuccessResponse(
    id: string | number | null,
    result: unknown
): JSONRPCSuccessResponse {
    return {
        jsonrpc: '2.0',
        id,
        result,
    };
}

/** 创建错误响应 */
export function createErrorResponse(
    id: string | number | null,
    code: number,
    message: string,
    data?: unknown
): JSONRPCErrorResponse {
    return {
        jsonrpc: '2.0',
        id,
        error: { code, message, data },
    };
}
