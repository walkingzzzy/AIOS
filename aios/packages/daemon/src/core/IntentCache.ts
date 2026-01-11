/**
 * 意图缓存
 * LRU 缓存直达匹配和意图分类结果
 */

import type { TaskAnalysis, ToolCall } from '../types/orchestrator.js';

interface CacheEntry<T> {
    value: T;
    timestamp: number;
}

/**
 * 意图缓存 - 减少重复分析开销
 */
export class IntentCache {
    private directMatchCache: Map<string, CacheEntry<ToolCall | null>> = new Map();
    private classificationCache: Map<string, CacheEntry<TaskAnalysis>> = new Map();
    private accessOrder: string[] = [];
    private maxCacheSize: number;
    private ttlMs: number;

    constructor(maxCacheSize: number = 100, ttlMs: number = 5 * 60 * 1000) {
        this.maxCacheSize = maxCacheSize;
        this.ttlMs = ttlMs;
    }

    /**
     * 获取直达匹配缓存
     */
    getDirectMatch(input: string): ToolCall | null | undefined {
        const entry = this.directMatchCache.get(input);
        if (entry && !this.isExpired(entry)) {
            this.updateAccessOrder(input);
            return entry.value;
        }
        return undefined;
    }

    /**
     * 设置直达匹配缓存
     */
    setDirectMatch(input: string, result: ToolCall | null): void {
        this.directMatchCache.set(input, {
            value: result,
            timestamp: Date.now(),
        });
        this.updateAccessOrder(input);
        this.evictIfNeeded();
    }

    /**
     * 获取分类缓存
     */
    getClassification(input: string): TaskAnalysis | undefined {
        const entry = this.classificationCache.get(input);
        if (entry && !this.isExpired(entry)) {
            this.updateAccessOrder(input);
            return entry.value;
        }
        return undefined;
    }

    /**
     * 设置分类缓存
     */
    setClassification(input: string, result: TaskAnalysis): void {
        this.classificationCache.set(input, {
            value: result,
            timestamp: Date.now(),
        });
        this.updateAccessOrder(input);
        this.evictIfNeeded();
    }

    /**
     * 清空缓存
     */
    clear(): void {
        this.directMatchCache.clear();
        this.classificationCache.clear();
        this.accessOrder = [];
    }

    /**
     * 获取当前缓存大小
     */
    get size(): number {
        return this.directMatchCache.size + this.classificationCache.size;
    }

    /**
     * 检查是否过期
     */
    private isExpired<T>(entry: CacheEntry<T>): boolean {
        return Date.now() - entry.timestamp > this.ttlMs;
    }

    /**
     * 更新访问顺序
     */
    private updateAccessOrder(key: string): void {
        const index = this.accessOrder.indexOf(key);
        if (index > -1) {
            this.accessOrder.splice(index, 1);
        }
        this.accessOrder.push(key);
    }

    /**
     * 驱逐过期/超量条目
     */
    private evictIfNeeded(): void {
        while (this.size > this.maxCacheSize && this.accessOrder.length > 0) {
            const oldest = this.accessOrder.shift();
            if (oldest) {
                this.directMatchCache.delete(oldest);
                this.classificationCache.delete(oldest);
            }
        }
    }
}
