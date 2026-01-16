/**
 * Security 模块导出
 */

// 类型
export type {
    CallbackAuthMethod,
    CallbackAuth,
    CallbackPayload,
    SignedCallback,
    SignatureVerifyResult,
    CallbackAuthManagerConfig,
} from './types.js';

// 回调鉴权
export {
    CallbackAuthManager,
    callbackAuthManager,
} from './CallbackAuthManager.js';

// 网络安全
export {
    NetworkGuard,
    networkGuard,
    type NetworkGuardConfig,
    type DomainCheckResult,
} from './NetworkGuard.js';
