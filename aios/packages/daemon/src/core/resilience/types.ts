/**
 * 容错重试模块类型定义
 */

/**
 * 错误类型
 */
export type ErrorType =
    | 'network'      // 网络错误
    | 'timeout'      // 超时
    | 'rate_limit'   // 速率限制
    | 'api_error'    // API 错误（可重试）
    | 'auth_error'   // 认证错误（不可重试）
    | 'validation'   // 验证错误（不可重试）
    | 'unknown';     // 未知错误

/**
 * 重试策略配置
 */
export interface RetryPolicyConfig {
    /** 最大重试次数 */
    maxRetries: number;
    /** 初始延迟 (ms) */
    initialDelay: number;
    /** 退避乘数 */
    backoffMultiplier: number;
    /** 最大延迟 (ms) */
    maxDelay: number;
    /** 可重试的错误类型 */
    retryableErrors: ErrorType[];
    /** 抖动因子 (0-1)，用于避免雷群效应 */
    jitter: number;
}

/**
 * 重试上下文
 */
export interface RetryContext {
    /** 当前重试次数 */
    attempt: number;
    /** 最大重试次数 */
    maxRetries: number;
    /** 下次重试延迟 (ms) */
    nextDelay: number;
    /** 总延迟时间 (ms) */
    totalDelay: number;
    /** 上次错误 */
    lastError?: Error;
    /** 错误类型 */
    errorType?: ErrorType;
}

/**
 * 检查点状态
 */
export interface CheckpointState {
    /** 任务 ID */
    taskId: string;
    /** 当前步骤索引 */
    stepIndex: number;
    /** 总步骤数 */
    totalSteps: number;
    /** 已完成步骤的结果 */
    completedResults: Array<{
        stepId: number;
        result: unknown;
        timestamp: number;
    }>;
    /** 上下文数据 */
    context: Record<string, unknown>;
    /** 创建时间 */
    createdAt: number;
    /** 更新时间 */
    updatedAt: number;
}

/**
 * 重试结果
 */
export interface RetryResult<T> {
    /** 是否成功 */
    success: boolean;
    /** 结果数据 */
    data?: T;
    /** 错误信息 */
    error?: Error;
    /** 重试次数 */
    attempts: number;
    /** 总耗时 (ms) */
    totalTime: number;
}
