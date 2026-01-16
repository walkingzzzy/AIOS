/**
 * Trace 模块类型定义
 */

/**
 * 追踪上下文
 */
export interface TraceContext {
    /** 全局追踪 ID（贯穿整个请求链路） */
    traceId: string;
    /** 单次请求 ID */
    requestId: string;
    /** 当前操作 Span ID */
    spanId: string;
    /** 父 Span ID */
    parentSpanId?: string;
    /** 开始时间戳 */
    startTime: number;
    /** 采样标志 */
    sampled?: boolean;
}

/**
 * Span 信息
 */
export interface SpanInfo {
    /** Span ID */
    spanId: string;
    /** 父 Span ID */
    parentSpanId?: string;
    /** 操作名称 */
    operation: string;
    /** 开始时间 */
    startTime: number;
    /** 结束时间 */
    endTime?: number;
    /** 持续时间（毫秒） */
    duration?: number;
    /** 状态 */
    status: 'ok' | 'error';
    /** 标签 */
    tags?: Record<string, string | number | boolean>;
    /** 日志事件 */
    logs?: Array<{
        timestamp: number;
        message: string;
    }>;
}

/**
 * TraceContextManager 配置
 */
export interface TraceContextManagerConfig {
    /** 采样率 (0-1) */
    sampleRate?: number;
    /** 服务名称 */
    serviceName?: string;
}

/**
 * TraceLogger 配置
 */
export interface TraceLoggerConfig {
    /** 是否启用 */
    enabled?: boolean;
    /** 日志级别 */
    level?: 'debug' | 'info' | 'warn' | 'error';
    /** 是否包含时间戳 */
    includeTimestamp?: boolean;
    /** 是否包含 traceId */
    includeTraceId?: boolean;
}

/**
 * 日志级别优先级
 */
export const LOG_LEVELS: Record<string, number> = {
    debug: 0,
    info: 1,
    warn: 2,
    error: 3,
};
