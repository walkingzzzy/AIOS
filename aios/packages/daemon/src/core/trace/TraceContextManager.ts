/**
 * TraceContextManager - 追踪上下文管理器
 * 使用 AsyncLocalStorage 实现上下文传递
 */

import { AsyncLocalStorage } from 'async_hooks';
import { randomUUID } from 'crypto';
import type { TraceContext, SpanInfo, TraceContextManagerConfig } from './types.js';

/**
 * 追踪上下文管理器
 */
export class TraceContextManager {
    private storage: AsyncLocalStorage<TraceContext>;
    private config: Required<TraceContextManagerConfig>;

    /** 活跃的 Span */
    private activeSpans: Map<string, SpanInfo>;

    constructor(config: TraceContextManagerConfig = {}) {
        this.storage = new AsyncLocalStorage();
        this.config = {
            sampleRate: config.sampleRate ?? 1.0,
            serviceName: config.serviceName ?? 'aios-daemon',
        };
        this.activeSpans = new Map();
    }

    /**
     * 创建新的追踪上下文
     */
    create(): TraceContext {
        const traceId = randomUUID().replace(/-/g, '');
        const requestId = randomUUID().replace(/-/g, '').substring(0, 16);
        const spanId = randomUUID().replace(/-/g, '').substring(0, 16);

        return {
            traceId,
            requestId,
            spanId,
            startTime: Date.now(),
            sampled: Math.random() < this.config.sampleRate,
        };
    }

    /**
     * 从 HTTP 头创建上下文
     */
    fromHeaders(headers: Record<string, string | undefined>): TraceContext {
        // 支持 W3C Trace Context 和 B3 格式
        const traceId = headers['x-trace-id'] ?? headers['traceparent']?.split('-')[1] ?? randomUUID().replace(/-/g, '');
        const parentSpanId = headers['x-span-id'] ?? headers['traceparent']?.split('-')[2];
        const requestId = headers['x-request-id'] ?? randomUUID().replace(/-/g, '').substring(0, 16);
        const spanId = randomUUID().replace(/-/g, '').substring(0, 16);

        return {
            traceId,
            requestId,
            spanId,
            parentSpanId,
            startTime: Date.now(),
            sampled: headers['x-sample'] !== '0',
        };
    }

    /**
     * 转换为 HTTP 头
     */
    toHeaders(ctx: TraceContext): Record<string, string> {
        return {
            'x-trace-id': ctx.traceId,
            'x-request-id': ctx.requestId,
            'x-span-id': ctx.spanId,
            'x-sample': ctx.sampled ? '1' : '0',
            // W3C Trace Context 格式
            'traceparent': `00-${ctx.traceId}-${ctx.spanId}-${ctx.sampled ? '01' : '00'}`,
        };
    }

    /**
     * 获取当前上下文
     */
    current(): TraceContext | undefined {
        return this.storage.getStore();
    }

    /**
     * 在上下文中运行函数
     */
    run<T>(ctx: TraceContext, fn: () => T): T {
        return this.storage.run(ctx, fn);
    }

    /**
     * 在上下文中运行异步函数
     */
    async runAsync<T>(ctx: TraceContext, fn: () => Promise<T>): Promise<T> {
        return this.storage.run(ctx, fn);
    }

    /**
     * 创建子 Span
     */
    createSpan(operation: string): SpanInfo {
        const ctx = this.current();
        const spanId = randomUUID().replace(/-/g, '').substring(0, 16);

        const span: SpanInfo = {
            spanId,
            parentSpanId: ctx?.spanId,
            operation,
            startTime: Date.now(),
            status: 'ok',
            tags: {},
            logs: [],
        };

        this.activeSpans.set(spanId, span);
        return span;
    }

    /**
     * 结束 Span
     */
    endSpan(spanId: string, status: 'ok' | 'error' = 'ok'): SpanInfo | undefined {
        const span = this.activeSpans.get(spanId);
        if (!span) return undefined;

        span.endTime = Date.now();
        span.duration = span.endTime - span.startTime;
        span.status = status;

        this.activeSpans.delete(spanId);
        return span;
    }

    /**
     * 添加 Span 标签
     */
    addSpanTag(spanId: string, key: string, value: string | number | boolean): void {
        const span = this.activeSpans.get(spanId);
        if (span) {
            span.tags = span.tags ?? {};
            span.tags[key] = value;
        }
    }

    /**
     * 添加 Span 日志
     */
    addSpanLog(spanId: string, message: string): void {
        const span = this.activeSpans.get(spanId);
        if (span) {
            span.logs = span.logs ?? [];
            span.logs.push({ timestamp: Date.now(), message });
        }
    }

    /**
     * 获取当前 traceId
     */
    getTraceId(): string | undefined {
        return this.current()?.traceId;
    }

    /**
     * 获取当前 spanId
     */
    getSpanId(): string | undefined {
        return this.current()?.spanId;
    }

    /**
     * 获取服务名称
     */
    getServiceName(): string {
        return this.config.serviceName;
    }

    /**
     * 是否应该采样
     */
    isSampled(): boolean {
        return this.current()?.sampled ?? true;
    }

    /**
     * 获取采样率
     */
    getSampleRate(): number {
        return this.config.sampleRate;
    }

    /**
     * 设置采样率
     */
    setSampleRate(rate: number): void {
        this.config.sampleRate = Math.max(0, Math.min(1, rate));
    }
}

/**
 * 默认实例
 */
export const traceContextManager = new TraceContextManager();
