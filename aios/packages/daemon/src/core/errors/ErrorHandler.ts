/**
 * ErrorHandler - 统一错误处理器
 * 处理各类错误并转换为标准格式
 */

import { ErrorCode, ERROR_MESSAGES } from './ErrorCode.js';
import { AppError } from './AppError.js';

/**
 * 错误处理结果
 */
export interface ErrorHandleResult {
    /** 是否已处理 */
    handled: boolean;
    /** 转换后的 AppError */
    error: AppError;
    /** 是否应该重试 */
    shouldRetry: boolean;
    /** 是否应该上报 */
    shouldReport: boolean;
}

/**
 * 错误处理器配置
 */
export interface ErrorHandlerConfig {
    /** 是否启用日志 */
    enableLogging?: boolean;
    /** 日志前缀 */
    logPrefix?: string;
    /** 错误上报回调 */
    onReport?: (error: AppError) => void | Promise<void>;
}

/**
 * AI API 错误响应格式
 */
interface AIAPIErrorResponse {
    error?: {
        message?: string;
        type?: string;
        code?: string;
    };
    status?: number;
}

/**
 * 统一错误处理器
 */
export class ErrorHandler {
    private config: Required<Omit<ErrorHandlerConfig, 'onReport'>> & Pick<ErrorHandlerConfig, 'onReport'>;

    constructor(config: ErrorHandlerConfig = {}) {
        this.config = {
            enableLogging: config.enableLogging ?? true,
            logPrefix: config.logPrefix ?? '[ErrorHandler]',
            onReport: config.onReport,
        };
    }

    /**
     * 处理错误
     */
    async handle(error: unknown): Promise<ErrorHandleResult> {
        const appError = this.normalize(error);

        if (this.config.enableLogging) {
            this.log(appError);
        }

        const shouldRetry = appError.recoverable && appError.retryAfter !== undefined;
        const shouldReport = this.shouldReport(appError);

        if (shouldReport && this.config.onReport) {
            try {
                await this.config.onReport(appError);
            } catch (reportError) {
                console.error(`${this.config.logPrefix} Failed to report error:`, reportError);
            }
        }

        return {
            handled: true,
            error: appError,
            shouldRetry,
            shouldReport,
        };
    }

    /**
     * 将任意错误标准化为 AppError
     */
    normalize(error: unknown): AppError {
        // 已经是 AppError
        if (error instanceof AppError) {
            return error;
        }

        // 标准 Error
        if (error instanceof Error) {
            return this.fromStandardError(error);
        }

        // 字符串
        if (typeof error === 'string') {
            return new AppError(ErrorCode.TASK_FAILED, error);
        }

        // 对象（可能是 API 错误响应）
        if (error && typeof error === 'object') {
            return this.fromErrorObject(error as Record<string, unknown>);
        }

        // 未知类型
        return new AppError(ErrorCode.TASK_FAILED, String(error));
    }

    /**
     * 从标准 Error 创建 AppError
     */
    private fromStandardError(error: Error): AppError {
        // 检测 AI 相关错误
        const aiError = this.detectAIError(error);
        if (aiError) {
            return aiError;
        }

        // 检测网络错误
        if (this.isNetworkError(error)) {
            return new AppError(ErrorCode.AI_SERVICE_UNAVAILABLE, error.message, {
                details: { cause: error },
            });
        }

        // 一般错误
        return AppError.fromError(error);
    }

    /**
     * 检测 AI 相关错误
     */
    private detectAIError(error: Error): AppError | null {
        const message = error.message.toLowerCase();

        // 速率限制
        if (message.includes('rate limit') || message.includes('429')) {
            return new AppError(ErrorCode.AI_RATE_LIMIT, error.message, {
                details: { cause: error },
            });
        }

        // 上下文溢出
        if (message.includes('context') && (message.includes('too long') || message.includes('overflow') || message.includes('exceeded'))) {
            return new AppError(ErrorCode.AI_CONTEXT_OVERFLOW, error.message, {
                details: { cause: error },
            });
        }

        // 认证失败
        if (message.includes('unauthorized') || message.includes('401') || message.includes('api key')) {
            return new AppError(ErrorCode.AI_AUTH_FAILED, error.message, {
                details: { cause: error },
            });
        }

        // 模型不支持
        if (message.includes('model') && (message.includes('not found') || message.includes('not supported'))) {
            return new AppError(ErrorCode.AI_MODEL_NOT_SUPPORTED, error.message, {
                details: { cause: error },
            });
        }

        return null;
    }

    /**
     * 从错误对象创建 AppError
     */
    private fromErrorObject(obj: Record<string, unknown>): AppError {
        // API 错误响应格式
        const apiError = obj as AIAPIErrorResponse;
        if (apiError.error) {
            const code = this.mapAPIErrorCode(apiError);
            return new AppError(code, apiError.error.message ?? 'API Error');
        }

        // 直接包含 code 和 message
        if (typeof obj['code'] === 'number' && typeof obj['message'] === 'string') {
            const code = this.isValidErrorCode(obj['code']) ? obj['code'] : ErrorCode.TASK_FAILED;
            return new AppError(code as ErrorCode, obj['message'] as string);
        }

        return new AppError(ErrorCode.TASK_FAILED, JSON.stringify(obj));
    }

    /**
     * 映射 API 错误码
     */
    private mapAPIErrorCode(response: AIAPIErrorResponse): ErrorCode {
        const status = response.status;
        const type = response.error?.type?.toLowerCase() ?? '';

        if (status === 429 || type.includes('rate')) {
            return ErrorCode.AI_RATE_LIMIT;
        }
        if (status === 401 || status === 403) {
            return ErrorCode.AI_AUTH_FAILED;
        }
        if (status === 503 || status === 502 || status === 500) {
            return ErrorCode.AI_SERVICE_UNAVAILABLE;
        }

        return ErrorCode.TASK_FAILED;
    }

    /**
     * 检查是否为网络错误
     */
    private isNetworkError(error: Error): boolean {
        const message = error.message.toLowerCase();
        return (
            message.includes('network') ||
            message.includes('econnrefused') ||
            message.includes('enotfound') ||
            message.includes('timeout') ||
            message.includes('socket')
        );
    }

    /**
     * 检查是否为有效的错误码
     */
    private isValidErrorCode(code: number): boolean {
        return Object.values(ErrorCode).includes(code);
    }

    /**
     * 判断错误是否需要上报
     */
    private shouldReport(error: AppError): boolean {
        // 不上报的错误类型
        const noReportCodes = new Set([
            ErrorCode.TASK_CANCELLED,
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.AI_RATE_LIMIT, // 常见，无需上报
        ]);

        return !noReportCodes.has(error.code);
    }

    /**
     * 记录错误日志
     */
    private log(error: AppError): void {
        const prefix = this.config.logPrefix;
        const details = error.details?.traceId ? ` [trace:${error.details.traceId}]` : '';

        console.error(
            `${prefix}${details} [${error.code}] ${error.message}`,
            error.recoverable ? '(recoverable)' : '(fatal)'
        );

        if (error.details?.cause) {
            console.error(`${prefix} Caused by:`, error.details.cause);
        }
    }

    /**
     * 创建 JSON-RPC 错误响应
     */
    static toJSONRPCResponse(error: AppError, id: string | number | null): {
        jsonrpc: '2.0';
        id: string | number | null;
        error: ReturnType<AppError['toJSONRPC']>;
    } {
        return {
            jsonrpc: '2.0',
            id,
            error: error.toJSONRPC(),
        };
    }
}

/**
 * 默认错误处理器实例
 */
export const errorHandler = new ErrorHandler();
