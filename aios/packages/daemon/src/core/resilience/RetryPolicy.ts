/**
 * RetryPolicy - 重试策略
 * 实现指数退避重试机制
 */

import type {
    RetryPolicyConfig,
    RetryContext,
    RetryResult,
    ErrorType,
} from './types.js';

/**
 * 默认策略配置
 */
const DEFAULT_CONFIG: RetryPolicyConfig = {
    maxRetries: 3,
    initialDelay: 1000,
    backoffMultiplier: 2,
    maxDelay: 30000,
    retryableErrors: ['network', 'timeout', 'rate_limit', 'api_error'],
    jitter: 0.2,
};

/**
 * 重试策略
 */
export class RetryPolicy {
    private config: RetryPolicyConfig;

    constructor(config: Partial<RetryPolicyConfig> = {}) {
        this.config = { ...DEFAULT_CONFIG, ...config };
    }

    /**
     * 执行带重试的操作
     */
    async execute<T>(
        operation: () => Promise<T>,
        onRetry?: (context: RetryContext) => void
    ): Promise<RetryResult<T>> {
        const startTime = Date.now();
        let lastError: Error | undefined;
        let totalDelay = 0;

        for (let attempt = 0; attempt <= this.config.maxRetries; attempt++) {
            try {
                const data = await operation();
                return {
                    success: true,
                    data,
                    attempts: attempt + 1,
                    totalTime: Date.now() - startTime,
                };
            } catch (error) {
                lastError = error instanceof Error ? error : new Error(String(error));
                const errorType = this.classifyError(lastError);

                // 检查是否可重试
                if (!this.isRetryable(errorType) || attempt >= this.config.maxRetries) {
                    return {
                        success: false,
                        error: lastError,
                        attempts: attempt + 1,
                        totalTime: Date.now() - startTime,
                    };
                }

                // 计算延迟
                const delay = this.calculateDelay(attempt);
                totalDelay += delay;

                const context: RetryContext = {
                    attempt: attempt + 1,
                    maxRetries: this.config.maxRetries,
                    nextDelay: delay,
                    totalDelay,
                    lastError,
                    errorType,
                };

                console.log(
                    `[RetryPolicy] Retry ${context.attempt}/${this.config.maxRetries}, ` +
                    `delay: ${delay}ms, error: ${lastError.message}`
                );

                // 通知回调
                onRetry?.(context);

                // 等待
                await this.sleep(delay);
            }
        }

        return {
            success: false,
            error: lastError,
            attempts: this.config.maxRetries + 1,
            totalTime: Date.now() - startTime,
        };
    }

    /**
     * 计算延迟时间（指数退避 + 抖动）
     */
    calculateDelay(attempt: number): number {
        // 指数退避
        let delay = this.config.initialDelay * Math.pow(this.config.backoffMultiplier, attempt);

        // 应用最大延迟限制
        delay = Math.min(delay, this.config.maxDelay);

        // 添加抖动
        if (this.config.jitter > 0) {
            const jitterRange = delay * this.config.jitter;
            const jitterAmount = (Math.random() * 2 - 1) * jitterRange;
            delay = Math.max(0, delay + jitterAmount);
        }

        return Math.round(delay);
    }

    /**
     * 分类错误类型
     */
    classifyError(error: Error): ErrorType {
        const message = error.message.toLowerCase();

        if (message.includes('timeout') || message.includes('timed out')) {
            return 'timeout';
        }
        if (message.includes('network') || message.includes('fetch') ||
            message.includes('econnrefused') || message.includes('enotfound')) {
            return 'network';
        }
        if (message.includes('rate limit') || message.includes('429') ||
            message.includes('too many requests')) {
            return 'rate_limit';
        }
        if (message.includes('unauthorized') || message.includes('401') ||
            message.includes('forbidden') || message.includes('403')) {
            return 'auth_error';
        }
        if (message.includes('validation') || message.includes('invalid') ||
            message.includes('400')) {
            return 'validation';
        }
        if (message.includes('500') || message.includes('502') ||
            message.includes('503') || message.includes('504')) {
            return 'api_error';
        }

        return 'unknown';
    }

    /**
     * 检查错误是否可重试
     */
    isRetryable(errorType: ErrorType): boolean {
        return this.config.retryableErrors.includes(errorType);
    }

    /**
     * 获取配置
     */
    getConfig(): RetryPolicyConfig {
        return { ...this.config };
    }

    /**
     * 睡眠
     */
    private sleep(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

/**
 * 预定义策略
 */
export const RETRY_POLICIES = {
    /** 快速重试 - 适用于轻量操作 */
    fast: new RetryPolicy({
        maxRetries: 3,
        initialDelay: 100,
        backoffMultiplier: 1.5,
        maxDelay: 2000,
    }),

    /** 标准重试 - 适用于一般 API 调用 */
    standard: new RetryPolicy({
        maxRetries: 3,
        initialDelay: 1000,
        backoffMultiplier: 2,
        maxDelay: 30000,
    }),

    /** 持久重试 - 适用于关键操作 */
    persistent: new RetryPolicy({
        maxRetries: 5,
        initialDelay: 2000,
        backoffMultiplier: 2,
        maxDelay: 60000,
    }),

    /** AI 调用重试 - 针对 LLM API 优化 */
    ai: new RetryPolicy({
        maxRetries: 3,
        initialDelay: 2000,
        backoffMultiplier: 2.5,
        maxDelay: 60000,
        retryableErrors: ['network', 'timeout', 'rate_limit', 'api_error'],
        jitter: 0.3,
    }),
};
