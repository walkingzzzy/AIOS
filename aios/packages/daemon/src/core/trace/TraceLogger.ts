/**
 * TraceLogger - 带追踪信息的日志记录器
 */

import { TraceContextManager, traceContextManager } from './TraceContextManager.js';
import { LOG_LEVELS, type TraceLoggerConfig } from './types.js';

/**
 * 日志条目
 */
export interface LogEntry {
    timestamp: string;
    level: string;
    traceId?: string;
    spanId?: string;
    message: string;
    data?: unknown;
}

/**
 * 带追踪信息的日志记录器
 */
export class TraceLogger {
    private contextManager: TraceContextManager;
    private config: Required<TraceLoggerConfig>;
    private name: string;

    constructor(
        name: string,
        config: TraceLoggerConfig = {},
        contextManager?: TraceContextManager
    ) {
        this.name = name;
        this.contextManager = contextManager ?? traceContextManager;
        this.config = {
            enabled: config.enabled ?? true,
            level: config.level ?? 'info',
            includeTimestamp: config.includeTimestamp ?? true,
            includeTraceId: config.includeTraceId ?? true,
        };
    }

    /**
     * 格式化日志消息
     */
    private format(level: string, message: string, data?: unknown): string {
        const parts: string[] = [];

        // 时间戳
        if (this.config.includeTimestamp) {
            parts.push(`[${new Date().toISOString()}]`);
        }

        // 级别
        parts.push(`[${level.toUpperCase()}]`);

        // 追踪信息
        if (this.config.includeTraceId) {
            const traceId = this.contextManager.getTraceId();
            const spanId = this.contextManager.getSpanId();
            if (traceId) {
                parts.push(`[trace:${traceId.substring(0, 8)}]`);
            }
            if (spanId) {
                parts.push(`[span:${spanId.substring(0, 8)}]`);
            }
        }

        // 名称
        parts.push(`[${this.name}]`);

        // 消息
        parts.push(message);

        // 数据
        if (data !== undefined) {
            if (typeof data === 'object') {
                parts.push(JSON.stringify(data));
            } else {
                parts.push(String(data));
            }
        }

        return parts.join(' ');
    }

    /**
     * 检查是否应该记录该级别
     */
    private shouldLog(level: string): boolean {
        if (!this.config.enabled) return false;
        return LOG_LEVELS[level] >= LOG_LEVELS[this.config.level];
    }

    /**
     * 记录 debug 日志
     */
    debug(message: string, data?: unknown): void {
        if (this.shouldLog('debug')) {
            console.debug(this.format('debug', message, data));
        }
    }

    /**
     * 记录 info 日志
     */
    info(message: string, data?: unknown): void {
        if (this.shouldLog('info')) {
            console.info(this.format('info', message, data));
        }
    }

    /**
     * 记录 warn 日志
     */
    warn(message: string, data?: unknown): void {
        if (this.shouldLog('warn')) {
            console.warn(this.format('warn', message, data));
        }
    }

    /**
     * 记录 error 日志
     */
    error(message: string, data?: unknown): void {
        if (this.shouldLog('error')) {
            console.error(this.format('error', message, data));
        }
    }

    /**
     * 创建子 logger
     */
    child(name: string): TraceLogger {
        return new TraceLogger(
            `${this.name}:${name}`,
            this.config,
            this.contextManager
        );
    }

    /**
     * 在追踪上下文中执行并记录
     */
    async trace<T>(
        operation: string,
        fn: () => Promise<T>
    ): Promise<T> {
        const span = this.contextManager.createSpan(operation);
        this.debug(`Starting ${operation}`);

        try {
            const result = await fn();
            this.contextManager.endSpan(span.spanId, 'ok');
            this.debug(`Completed ${operation}`, { duration: Date.now() - span.startTime });
            return result;
        } catch (error) {
            this.contextManager.endSpan(span.spanId, 'error');
            this.error(`Failed ${operation}`, error);
            throw error;
        }
    }

    /**
     * 获取配置
     */
    getConfig(): Required<TraceLoggerConfig> {
        return { ...this.config };
    }

    /**
     * 设置日志级别
     */
    setLevel(level: 'debug' | 'info' | 'warn' | 'error'): void {
        this.config.level = level;
    }

    /**
     * 启用/禁用
     */
    setEnabled(enabled: boolean): void {
        this.config.enabled = enabled;
    }
}

/**
 * 创建 logger 工厂函数
 */
export function createLogger(name: string, config?: TraceLoggerConfig): TraceLogger {
    return new TraceLogger(name, config);
}
