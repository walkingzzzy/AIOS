/**
 * ErrorCode - 统一错误码枚举
 * 遵循 JSON-RPC 2.0 规范，使用负数错误码
 */

/**
 * 错误码枚举
 * -32000 ~ -32099: 服务器保留（JSON-RPC 规范）
 * -32100 ~ -32199: 任务相关
 * -32200 ~ -32299: 会话相关
 * -32300 ~ -32399: 工作区相关
 * -32400 ~ -32499: 适配器相关
 * -32500 ~ -32599: AI 相关
 * -32600 ~ -32699: 安全相关
 */
export enum ErrorCode {
    // ==================== 任务相关 (-32100 ~ -32199) ====================
    /** 任务未找到 */
    TASK_NOT_FOUND = -32100,
    /** 任务已在运行中 */
    TASK_ALREADY_RUNNING = -32101,
    /** 任务已取消 */
    TASK_CANCELLED = -32102,
    /** 任务执行超时 */
    TASK_TIMEOUT = -32103,
    /** 任务执行失败 */
    TASK_FAILED = -32104,
    /** 无效的任务类型 */
    INVALID_TASK_TYPE = -32105,
    /** 队列已满 */
    QUEUE_FULL = -32106,

    // ==================== 会话相关 (-32200 ~ -32299) ====================
    /** 会话未找到 */
    SESSION_NOT_FOUND = -32200,
    /** 会话已过期 */
    SESSION_EXPIRED = -32201,
    /** 无效的会话状态 */
    INVALID_SESSION_STATE = -32202,
    /** 会话已关闭 */
    SESSION_CLOSED = -32203,

    // ==================== 工作区相关 (-32300 ~ -32399) ====================
    /** 工作区未找到 */
    WORKSPACE_NOT_FOUND = -32300,
    /** 工作区被锁定 */
    WORKSPACE_LOCKED = -32301,
    /** 磁盘空间不足 */
    WORKSPACE_DISK_FULL = -32302,
    /** 工作区已存在 */
    WORKSPACE_EXISTS = -32303,
    /** 工作区归档失败 */
    WORKSPACE_ARCHIVE_FAILED = -32304,

    // ==================== 适配器相关 (-32400 ~ -32499) ====================
    /** 适配器未找到 */
    ADAPTER_NOT_FOUND = -32400,
    /** 能力未找到 */
    CAPABILITY_NOT_FOUND = -32401,
    /** 权限被拒绝 */
    PERMISSION_DENIED = -32402,
    /** 适配器执行失败 */
    ADAPTER_EXECUTION_FAILED = -32403,
    /** 适配器初始化失败 */
    ADAPTER_INIT_FAILED = -32404,
    /** 无效的参数 */
    INVALID_PARAMS = -32405,

    // ==================== AI 相关 (-32500 ~ -32599) ====================
    /** AI 速率限制 */
    AI_RATE_LIMIT = -32500,
    /** 上下文溢出 */
    AI_CONTEXT_OVERFLOW = -32501,
    /** AI 响应无效 */
    AI_INVALID_RESPONSE = -32502,
    /** AI 服务不可用 */
    AI_SERVICE_UNAVAILABLE = -32503,
    /** AI 认证失败 */
    AI_AUTH_FAILED = -32504,
    /** 模型不支持 */
    AI_MODEL_NOT_SUPPORTED = -32505,

    // ==================== 安全相关 (-32600 ~ -32699) ====================
    /** 回调签名无效 */
    CALLBACK_SIGNATURE_INVALID = -32600,
    /** 回调已过期 */
    CALLBACK_EXPIRED = -32601,
    /** 检测到注入攻击 */
    INJECTION_DETECTED = -32602,
    /** 高风险操作未确认 */
    HIGH_RISK_UNCONFIRMED = -32603,
    /** Token 无效 */
    INVALID_TOKEN = -32604,
}

/**
 * 错误码描述映射
 */
export const ERROR_MESSAGES: Record<ErrorCode, string> = {
    // 任务相关
    [ErrorCode.TASK_NOT_FOUND]: '任务未找到',
    [ErrorCode.TASK_ALREADY_RUNNING]: '任务已在运行中',
    [ErrorCode.TASK_CANCELLED]: '任务已取消',
    [ErrorCode.TASK_TIMEOUT]: '任务执行超时',
    [ErrorCode.TASK_FAILED]: '任务执行失败',
    [ErrorCode.INVALID_TASK_TYPE]: '无效的任务类型',
    [ErrorCode.QUEUE_FULL]: '任务队列已满',

    // 会话相关
    [ErrorCode.SESSION_NOT_FOUND]: '会话未找到',
    [ErrorCode.SESSION_EXPIRED]: '会话已过期',
    [ErrorCode.INVALID_SESSION_STATE]: '无效的会话状态',
    [ErrorCode.SESSION_CLOSED]: '会话已关闭',

    // 工作区相关
    [ErrorCode.WORKSPACE_NOT_FOUND]: '工作区未找到',
    [ErrorCode.WORKSPACE_LOCKED]: '工作区被锁定',
    [ErrorCode.WORKSPACE_DISK_FULL]: '磁盘空间不足',
    [ErrorCode.WORKSPACE_EXISTS]: '工作区已存在',
    [ErrorCode.WORKSPACE_ARCHIVE_FAILED]: '工作区归档失败',

    // 适配器相关
    [ErrorCode.ADAPTER_NOT_FOUND]: '适配器未找到',
    [ErrorCode.CAPABILITY_NOT_FOUND]: '能力未找到',
    [ErrorCode.PERMISSION_DENIED]: '权限被拒绝',
    [ErrorCode.ADAPTER_EXECUTION_FAILED]: '适配器执行失败',
    [ErrorCode.ADAPTER_INIT_FAILED]: '适配器初始化失败',
    [ErrorCode.INVALID_PARAMS]: '无效的参数',

    // AI 相关
    [ErrorCode.AI_RATE_LIMIT]: 'AI 服务速率限制',
    [ErrorCode.AI_CONTEXT_OVERFLOW]: '上下文长度超出限制',
    [ErrorCode.AI_INVALID_RESPONSE]: 'AI 响应格式无效',
    [ErrorCode.AI_SERVICE_UNAVAILABLE]: 'AI 服务不可用',
    [ErrorCode.AI_AUTH_FAILED]: 'AI 服务认证失败',
    [ErrorCode.AI_MODEL_NOT_SUPPORTED]: '不支持的 AI 模型',

    // 安全相关
    [ErrorCode.CALLBACK_SIGNATURE_INVALID]: '回调签名无效',
    [ErrorCode.CALLBACK_EXPIRED]: '回调已过期',
    [ErrorCode.INJECTION_DETECTED]: '检测到潜在的注入攻击',
    [ErrorCode.HIGH_RISK_UNCONFIRMED]: '高风险操作需要用户确认',
    [ErrorCode.INVALID_TOKEN]: '无效的认证令牌',
};

/**
 * 判断错误码是否可重试
 */
export function isRetryableError(code: ErrorCode): boolean {
    const retryableCodes = new Set([
        ErrorCode.TASK_TIMEOUT,
        ErrorCode.AI_RATE_LIMIT,
        ErrorCode.AI_SERVICE_UNAVAILABLE,
        ErrorCode.WORKSPACE_LOCKED,
    ]);
    return retryableCodes.has(code);
}

/**
 * 获取推荐的重试等待时间（毫秒）
 */
export function getRetryAfter(code: ErrorCode): number | undefined {
    const retryAfterMap: Partial<Record<ErrorCode, number>> = {
        [ErrorCode.AI_RATE_LIMIT]: 60000, // 1 分钟
        [ErrorCode.AI_SERVICE_UNAVAILABLE]: 5000, // 5 秒
        [ErrorCode.WORKSPACE_LOCKED]: 1000, // 1 秒
        [ErrorCode.TASK_TIMEOUT]: 0, // 立即重试
    };
    return retryAfterMap[code];
}
