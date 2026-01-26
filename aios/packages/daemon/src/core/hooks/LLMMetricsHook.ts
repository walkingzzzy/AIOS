/**
 * LLMMetricsHook - LLM 指标收集 Hook
 * 收集 LLM 请求的延迟、Token 使用量、成功率等指标
 */

import { BaseHook } from './BaseHook.js';
import { HookPriority } from './types.js';
import type {
    LLMRequestEvent,
    LLMResponseEvent,
    LLMStreamChunkEvent,
} from './types.js';

/** 单次请求指标 */
interface RequestMetrics {
    requestId: string;
    engineId: string;
    model: string;
    startTime: number;
    endTime?: number;
    latency?: number;
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
    success: boolean;
    isStream: boolean;
    chunkCount?: number;
}

/** 聚合指标 */
interface AggregateMetrics {
    totalRequests: number;
    successfulRequests: number;
    failedRequests: number;
    totalPromptTokens: number;
    totalCompletionTokens: number;
    totalTokens: number;
    averageLatency: number;
    minLatency: number;
    maxLatency: number;
    streamRequests: number;
    averageChunksPerStream: number;
}

/**
 * LLM 指标收集 Hook
 */
export class LLMMetricsHook extends BaseHook {
    private metrics: Map<string, RequestMetrics> = new Map();
    private aggregate: AggregateMetrics = {
        totalRequests: 0,
        successfulRequests: 0,
        failedRequests: 0,
        totalPromptTokens: 0,
        totalCompletionTokens: 0,
        totalTokens: 0,
        averageLatency: 0,
        minLatency: Infinity,
        maxLatency: 0,
        streamRequests: 0,
        averageChunksPerStream: 0,
    };

    /** 最大保留的请求记录数 */
    private maxRecords: number;

    constructor(options: { maxRecords?: number } = {}) {
        super('llm-metrics', {
            description: '收集 LLM 请求指标：延迟、Token 使用量、成功率等',
            priority: HookPriority.LOW,
        });
        this.maxRecords = options.maxRecords ?? 1000;
    }

    getName(): string {
        return 'llm-metrics';
    }

    getDescription(): string {
        return '收集 LLM 请求指标：延迟、Token 使用量、成功率等';
    }

    getPriority(): number {
        return HookPriority.LOW; // 低优先级，最后执行
    }

    /**
     * LLM 请求开始
     */
    async onLLMRequest(event: LLMRequestEvent): Promise<void> {
        const metrics: RequestMetrics = {
            requestId: event.requestId,
            engineId: event.engineId,
            model: event.model,
            startTime: event.timestamp,
            success: false,
            isStream: event.options?.stream ?? false,
            chunkCount: 0,
        };

        this.metrics.set(event.requestId, metrics);
        this.aggregate.totalRequests++;

        // 清理旧记录
        this.pruneOldRecords();
    }

    /**
     * LLM 响应完成
     */
    async onLLMResponse(event: LLMResponseEvent): Promise<void> {
        const metrics = this.metrics.get(event.requestId);
        if (!metrics) return;

        metrics.endTime = event.timestamp;
        metrics.latency = event.latency;
        metrics.success = true;
        metrics.promptTokens = event.usage?.promptTokens;
        metrics.completionTokens = event.usage?.completionTokens;
        metrics.totalTokens = event.usage?.totalTokens;

        // 更新聚合指标
        this.aggregate.successfulRequests++;
        this.updateAggregateLatency(event.latency);

        if (event.usage) {
            this.aggregate.totalPromptTokens += event.usage.promptTokens;
            this.aggregate.totalCompletionTokens += event.usage.completionTokens;
            this.aggregate.totalTokens += event.usage.totalTokens;
        }
    }

    /**
     * 流式块事件
     */
    async onLLMStreamChunk(event: LLMStreamChunkEvent): Promise<void> {
        const metrics = this.metrics.get(event.requestId);
        if (!metrics) return;

        metrics.chunkCount = (metrics.chunkCount ?? 0) + 1;

        if (event.finished) {
            metrics.endTime = event.timestamp;
            metrics.latency = event.timestamp - metrics.startTime;
            metrics.success = true;
            this.aggregate.successfulRequests++;
            this.aggregate.streamRequests++;
            this.updateAggregateLatency(metrics.latency);
            this.updateStreamChunkAverage(metrics.chunkCount);
        }
    }

    /**
     * 获取单个请求的指标
     */
    getRequestMetrics(requestId: string): RequestMetrics | undefined {
        return this.metrics.get(requestId);
    }

    /**
     * 获取聚合指标
     */
    getAggregateMetrics(): AggregateMetrics {
        return { ...this.aggregate };
    }

    /**
     * 获取最近 N 个请求的指标
     */
    getRecentMetrics(count: number = 10): RequestMetrics[] {
        const entries = Array.from(this.metrics.values());
        return entries.slice(-count);
    }

    /**
     * 获取按模型分组的统计
     */
    getMetricsByModel(): Map<string, {
        requests: number;
        totalTokens: number;
        averageLatency: number;
    }> {
        const byModel = new Map<string, {
            requests: number;
            totalTokens: number;
            totalLatency: number;
        }>();

        for (const metrics of this.metrics.values()) {
            const existing = byModel.get(metrics.model) ?? {
                requests: 0,
                totalTokens: 0,
                totalLatency: 0,
            };

            existing.requests++;
            existing.totalTokens += metrics.totalTokens ?? 0;
            existing.totalLatency += metrics.latency ?? 0;

            byModel.set(metrics.model, existing);
        }

        // 计算平均值
        const result = new Map<string, {
            requests: number;
            totalTokens: number;
            averageLatency: number;
        }>();

        for (const [model, stats] of byModel) {
            result.set(model, {
                requests: stats.requests,
                totalTokens: stats.totalTokens,
                averageLatency: stats.requests > 0 ? stats.totalLatency / stats.requests : 0,
            });
        }

        return result;
    }

    /**
     * 重置所有指标
     */
    reset(): void {
        this.metrics.clear();
        this.aggregate = {
            totalRequests: 0,
            successfulRequests: 0,
            failedRequests: 0,
            totalPromptTokens: 0,
            totalCompletionTokens: 0,
            totalTokens: 0,
            averageLatency: 0,
            minLatency: Infinity,
            maxLatency: 0,
            streamRequests: 0,
            averageChunksPerStream: 0,
        };
    }

    private updateAggregateLatency(latency: number): void {
        this.aggregate.minLatency = Math.min(this.aggregate.minLatency, latency);
        this.aggregate.maxLatency = Math.max(this.aggregate.maxLatency, latency);

        // 移动平均
        const n = this.aggregate.successfulRequests;
        this.aggregate.averageLatency =
            (this.aggregate.averageLatency * (n - 1) + latency) / n;
    }

    private updateStreamChunkAverage(chunkCount: number): void {
        const n = this.aggregate.streamRequests;
        this.aggregate.averageChunksPerStream =
            (this.aggregate.averageChunksPerStream * (n - 1) + chunkCount) / n;
    }

    private pruneOldRecords(): void {
        if (this.metrics.size > this.maxRecords) {
            const keysToDelete = Array.from(this.metrics.keys()).slice(
                0,
                this.metrics.size - this.maxRecords
            );
            for (const key of keysToDelete) {
                this.metrics.delete(key);
            }
        }
    }
}
