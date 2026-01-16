/**
 * Security 模块类型定义
 */

/**
 * 回调认证方式
 */
export type CallbackAuthMethod = 'hmac' | 'token';

/**
 * 回调认证配置
 */
export interface CallbackAuth {
    /** 认证方式 */
    method: CallbackAuthMethod;
    /** HMAC 密钥 (用于 hmac 方式) */
    secret?: string;
    /** Token (用于 token 方式) */
    token?: string;
    /** 过期时间戳 (用于 token 方式) */
    expiresAt?: number;
}

/**
 * 回调事件 (来自 CallbackHook)
 */
export interface CallbackPayload {
    type: string;
    taskId: string;
    timestamp: number;
    data: unknown;
}

/**
 * 签名后的回调
 */
export interface SignedCallback {
    /** 原始负载 */
    payload: CallbackPayload;
    /** 签名 */
    signature: string;
    /** 签名时间戳 */
    timestamp: number;
    /** 签名算法 */
    algorithm: 'hmac-sha256';
}

/**
 * 签名验证结果
 */
export interface SignatureVerifyResult {
    /** 是否有效 */
    valid: boolean;
    /** 错误原因 */
    reason?: 'invalid_signature' | 'expired' | 'missing_data' | 'algorithm_mismatch';
    /** 时间偏移（毫秒，用于调试） */
    timeOffset?: number;
}

/**
 * CallbackAuthManager 配置
 */
export interface CallbackAuthManagerConfig {
    /** 默认密钥 */
    secret?: string;
    /** 时间窗口（毫秒，默认 5 分钟） */
    timeWindow?: number;
    /** 是否启用严格模式（拒绝无签名回调） */
    strictMode?: boolean;
}
