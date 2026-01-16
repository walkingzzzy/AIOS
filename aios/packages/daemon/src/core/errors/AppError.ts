/**
 * AppError - 应用错误类
 * 统一的错误类型，包含错误码、可恢复性等信息
 */

import { ErrorCode, ERROR_MESSAGES, isRetryableError, getRetryAfter } from './ErrorCode.js';

/**
 * 错误详情
 */
export interface ErrorDetails {
    /** 原始错误 */
    cause?: Error;
    /** 相关上下文 */
    context?: Record<string, unknown>;
    /** 追踪 ID */
    traceId?: string;
    /** 请求 ID */
    requestId?: string;
}

/**
 * 应用错误类
 */
export class AppError extends Error {
    /** 错误码 */
    readonly code: ErrorCode;

    /** 是否可恢复 */
    readonly recoverable: boolean;

    /** 重试等待时间（毫秒） */
    readonly retryAfter?: number;

    /** 错误详情 */
    readonly details?: ErrorDetails;

    /** 创建时间戳 */
    readonly timestamp: number;

    constructor(
        code: ErrorCode,
        message?: string,
        options?: {
            recoverable?: boolean;
            retryAfter?: number;
            details?: ErrorDetails;
        }
    ) {
        const finalMessage = message ?? ERROR_MESSAGES[code] ?? 'Unknown error';
        super(finalMessage);

        this.name = 'AppError';
        this.code = code;
        this.recoverable = options?.recoverable ?? isRetryableError(code);
        this.retryAfter = options?.retryAfter ?? getRetryAfter(code);
        this.details = options?.details;
        this.timestamp = Date.now();

        // 保持原型链
        Object.setPrototypeOf(this, AppError.prototype);

        // 捕获堆栈
        if (Error.captureStackTrace) {
            Error.captureStackTrace(this, AppError);
        }

        // 如果有原始错误，合并堆栈
        if (options?.details?.cause) {
            this.stack = `${this.stack}\nCaused by: ${options.details.cause.stack}`;
        }
    }

    /**
     * 转换为 JSON-RPC 错误格式
     */
    toJSONRPC(): {
        code: number;
        message: string;
        data?: {
            recoverable: boolean;
            retryAfter?: number;
            traceId?: string;
            timestamp: number;
        };
    } {
        return {
            code: this.code,
            message: this.message,
            data: {
                recoverable: this.recoverable,
                retryAfter: this.retryAfter,
                traceId: this.details?.traceId,
                timestamp: this.timestamp,
            },
        };
    }

    /**
     * 转换为普通对象
     */
    toJSON(): Record<string, unknown> {
        return {
            name: this.name,
            code: this.code,
            message: this.message,
            recoverable: this.recoverable,
            retryAfter: this.retryAfter,
            details: this.details,
            timestamp: this.timestamp,
            stack: this.stack,
        };
    }

    /**
     * 从普通 Error 创建 AppError
     */
    static fromError(error: Error, code: ErrorCode = ErrorCode.TASK_FAILED): AppError {
        if (error instanceof AppError) {
            return error;
        }

        return new AppError(code, error.message, {
            details: { cause: error },
        });
    }

    /**
     * 快速创建常见错误
     */
    static taskNotFound(taskId: string): AppError {
        return new AppError(ErrorCode.TASK_NOT_FOUND, `任务 ${taskId} 未找到`, {
            details: { context: { taskId } },
        });
    }

    static sessionNotFound(sessionId: string): AppError {
        return new AppError(ErrorCode.SESSION_NOT_FOUND, `会话 ${sessionId} 未找到`, {
            details: { context: { sessionId } },
        });
    }

    static adapterNotFound(adapterId: string): AppError {
        return new AppError(ErrorCode.ADAPTER_NOT_FOUND, `适配器 ${adapterId} 未找到`, {
            details: { context: { adapterId } },
        });
    }

    static capabilityNotFound(adapterId: string, capabilityId: string): AppError {
        return new AppError(
            ErrorCode.CAPABILITY_NOT_FOUND,
            `适配器 ${adapterId} 不支持能力 ${capabilityId}`,
            { details: { context: { adapterId, capabilityId } } }
        );
    }

    static permissionDenied(resource: string): AppError {
        return new AppError(ErrorCode.PERMISSION_DENIED, `无权访问资源: ${resource}`, {
            details: { context: { resource } },
        });
    }

    static aiRateLimit(model: string, retryAfter?: number): AppError {
        return new AppError(ErrorCode.AI_RATE_LIMIT, `AI 模型 ${model} 速率限制`, {
            retryAfter: retryAfter ?? 60000,
            details: { context: { model } },
        });
    }

    static invalidParams(message: string): AppError {
        return new AppError(ErrorCode.INVALID_PARAMS, message);
    }

    static timeout(operation: string, timeoutMs: number): AppError {
        return new AppError(ErrorCode.TASK_TIMEOUT, `操作 ${operation} 超时 (${timeoutMs}ms)`, {
            details: { context: { operation, timeoutMs } },
        });
    }
}
