/**
 * AI 引擎缓存包装器
 * 为 AI 调用添加 LRU 缓存机制以提高性能和降低成本
 */

import type { IAIEngine, Message, ChatResponse, ToolDefinition, StreamChunk, StreamOptions } from '@aios/shared';
import crypto from 'crypto';

/** 缓存条目 */
interface CacheEntry {
    response: ChatResponse;
    timestamp: number;
    hits: number;
}

/** LRU 缓存节点 */
class CacheNode<T> {
    key: string;
    value: T;
    prev: CacheNode<T> | null = null;
    next: CacheNode<T> | null = null;

    constructor(key: string, value: T) {
        this.key = key;
        this.value = value;
    }
}

/** LRU 缓存实现 */
class LRUCache<T> {
    private capacity: number;
    private cache: Map<string, CacheNode<T>>;
    private head: CacheNode<T>;
    private tail: CacheNode<T>;

    constructor(capacity: number = 100) {
        this.capacity = capacity;
        this.cache = new Map();

        // 创建虚拟头尾节点
        this.head = new CacheNode('', {} as T);
        this.tail = new CacheNode('', {} as T);
        this.head.next = this.tail;
        this.tail.prev = this.head;
    }

    get(key: string): T | null {
        const node = this.cache.get(key);
        if (!node) return null;

        // 移动到头部（最近使用）
        this.moveToHead(node);
        return node.value;
    }

    set(key: string, value: T): void {
        const existingNode = this.cache.get(key);

        if (existingNode) {
            existingNode.value = value;
            this.moveToHead(existingNode);
        } else {
            const newNode = new CacheNode(key, value);
            this.cache.set(key, newNode);
            this.addToHead(newNode);

            if (this.cache.size > this.capacity) {
                const removed = this.removeTail();
                if (removed) {
                    this.cache.delete(removed.key);
                }
            }
        }
    }

    private moveToHead(node: CacheNode<T>): void {
        this.removeNode(node);
        this.addToHead(node);
    }

    private removeNode(node: CacheNode<T>): void {
        if (node.prev) node.prev.next = node.next;
        if (node.next) node.next.prev = node.prev;
    }

    private addToHead(node: CacheNode<T>): void {
        node.prev = this.head;
        node.next = this.head.next;
        if (this.head.next) this.head.next.prev = node;
        this.head.next = node;
    }

    private removeTail(): CacheNode<T> | null {
        const node = this.tail.prev;
        if (node === this.head) return null;
        this.removeNode(node!);
        return node;
    }

    clear(): void {
        this.cache.clear();
        this.head.next = this.tail;
        this.tail.prev = this.head;
    }

    get size(): number {
        return this.cache.size;
    }
}

/** 缓存配置 */
export interface CacheConfig {
    /** 缓存容量 */
    maxSize?: number;
    /** 缓存过期时间（毫秒） */
    ttl?: number;
    /** 是否启用缓存 */
    enabled?: boolean;
    /** 是否缓存工具调用 */
    cacheToolCalls?: boolean;
}

/**
 * AI 引擎缓存包装器
 */
export class CachedAIEngine implements IAIEngine {
    private engine: IAIEngine;
    private cache: LRUCache<CacheEntry>;
    private config: Required<CacheConfig>;
    private hits: number = 0;
    private misses: number = 0;

    constructor(engine: IAIEngine, config?: CacheConfig) {
        this.engine = engine;
        this.config = {
            maxSize: config?.maxSize || 100,
            ttl: config?.ttl || 3600000, // 1小时
            enabled: config?.enabled !== false,
            cacheToolCalls: config?.cacheToolCalls !== false,
        };
        this.cache = new LRUCache(this.config.maxSize);
    }

    // IAIEngine 接口实现
    get id(): string {
        return this.engine.id;
    }

    get name(): string {
        return this.engine.name;
    }

    get provider() {
        return this.engine.provider;
    }

    get model(): string {
        return this.engine.model;
    }

    supportsVision(): boolean {
        return this.engine.supportsVision();
    }

    supportsToolCalling(): boolean {
        return this.engine.supportsToolCalling();
    }

    getMaxTokens(): number {
        return this.engine.getMaxTokens();
    }

    /**
     * 生成缓存键
     */
    private generateCacheKey(messages: Message[], tools?: ToolDefinition[]): string {
        const data = {
            messages: messages.map(m => ({
                role: m.role,
                content: m.content,
                // 不包含 images，因为图片内容可能很大
            })),
            tools: tools?.map(t => t.function.name),
        };
        const hash = crypto.createHash('sha256');
        hash.update(JSON.stringify(data));
        return hash.digest('hex');
    }

    /**
     * 检查缓存是否过期
     */
    private isExpired(entry: CacheEntry): boolean {
        return Date.now() - entry.timestamp > this.config.ttl;
    }

    /**
     * 聊天（带缓存）
     */
    async chat(messages: Message[]): Promise<ChatResponse> {
        if (!this.config.enabled) {
            return this.engine.chat(messages);
        }

        const cacheKey = this.generateCacheKey(messages);
        const cached = this.cache.get(cacheKey);

        if (cached && !this.isExpired(cached)) {
            this.hits++;
            cached.hits++;
            return { ...cached.response };
        }

        this.misses++;
        const response = await this.engine.chat(messages);

        const entry: CacheEntry = {
            response,
            timestamp: Date.now(),
            hits: 0,
        };
        this.cache.set(cacheKey, entry);

        return response;
    }

    /**
     * 聊天（带工具调用，带缓存）
     */
    async chatWithTools(messages: Message[], tools: ToolDefinition[]): Promise<ChatResponse> {
        if (!this.config.enabled || !this.config.cacheToolCalls) {
            return this.engine.chatWithTools(messages, tools);
        }

        const cacheKey = this.generateCacheKey(messages, tools);
        const cached = this.cache.get(cacheKey);

        if (cached && !this.isExpired(cached)) {
            this.hits++;
            cached.hits++;
            return { ...cached.response };
        }

        this.misses++;
        const response = await this.engine.chatWithTools(messages, tools);

        const entry: CacheEntry = {
            response,
            timestamp: Date.now(),
            hits: 0,
        };
        this.cache.set(cacheKey, entry);

        return response;
    }

    /**
     * 流式聊天（不走缓存，直接透传到底层引擎）
     */
    chatStream(
        messages: Message[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown> {
        return this.engine.chatStream(messages, options);
    }

    /**
     * 流式带工具调用的聊天（不走缓存，直接透传到底层引擎）
     */
    chatStreamWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown> {
        return this.engine.chatStreamWithTools(messages, tools, options);
    }

    /**
     * 是否支持流式响应
     */
    supportsStreaming(): boolean {
        return this.engine.supportsStreaming();
    }    /**
     * 获取缓存统计信息
     */
    getCacheStats() {
        const total = this.hits + this.misses;
        const hitRate = total > 0 ? (this.hits / total) * 100 : 0;
        const costSavings = this.hits; // 每次命中节省一次 API 调用

        return {
            hits: this.hits,
            misses: this.misses,
            total,
            hitRate: hitRate.toFixed(2) + '%',
            size: this.cache.size,
            costSavings,
            enabled: this.config.enabled,
        };
    }

    /**
     * 清空缓存
     */
    clearCache(): void {
        this.cache.clear();
        this.hits = 0;
        this.misses = 0;
    }

    /**
     * 启用/禁用缓存
     */
    setCacheEnabled(enabled: boolean): void {
        this.config.enabled = enabled;
        if (!enabled) {
            this.clearCache();
        }
    }

    /**
     * 设置缓存 TTL
     */
    setCacheTTL(ttl: number): void {
        this.config.ttl = ttl;
    }

    /**
     * 预热缓存
     */
    async warmup(commonQueries: Array<{ messages: Message[]; tools?: ToolDefinition[] }>): Promise<void> {
        for (const query of commonQueries) {
            try {
                if (query.tools) {
                    await this.chatWithTools(query.messages, query.tools);
                } else {
                    await this.chat(query.messages);
                }
            } catch (error) {
                console.error('Cache warmup failed for query:', error);
            }
        }
    }

    /**
     * 获取底层引擎
     */
    getUnderlyingEngine(): IAIEngine {
        return this.engine;
    }
}

/**
 * 创建带缓存的 AI 引擎
 */
export function createCachedEngine(engine: IAIEngine, config?: CacheConfig): CachedAIEngine {
    return new CachedAIEngine(engine, config);
}
