/**
 * EventStream - 统一事件流系统
 * 提供事件的发布、订阅、存储和回放功能
 */

import { EventEmitter } from 'events';

/** 事件类型枚举 */
export enum EventType {
    // 任务生命周期
    TASK_START = 'task:start',
    TASK_PROGRESS = 'task:progress',
    TASK_COMPLETE = 'task:complete',
    TASK_ERROR = 'task:error',

    // 工具调用
    TOOL_CALL = 'tool:call',
    TOOL_RESULT = 'tool:result',

    // LLM 生命周期
    LLM_REQUEST = 'llm:request',
    LLM_RESPONSE = 'llm:response',
    LLM_STREAM_CHUNK = 'llm:stream-chunk',

    // 系统事件
    SYSTEM_INFO = 'system:info',
    SYSTEM_WARNING = 'system:warning',
    SYSTEM_ERROR = 'system:error',
}

/** 基础事件结构 */
export interface BaseEvent {
    /** 事件 ID */
    id: string;
    /** 事件类型 */
    type: EventType;
    /** 时间戳 */
    timestamp: number;
    /** 来源组件 */
    source: string;
    /** 关联的任务 ID */
    taskId?: string;
    /** 关联的追踪 ID */
    traceId?: string;
    /** 事件数据 */
    data: Record<string, unknown>;
}

/** 事件过滤器 */
export interface EventFilter {
    /** 事件类型过滤 */
    types?: EventType[];
    /** 任务 ID 过滤 */
    taskId?: string;
    /** 来源过滤 */
    source?: string;
    /** 时间范围 - 开始 */
    startTime?: number;
    /** 时间范围 - 结束 */
    endTime?: number;
}

/** 订阅选项 */
export interface SubscriptionOptions {
    /** 过滤器 */
    filter?: EventFilter;
    /** 是否包含历史事件 */
    includeHistory?: boolean;
    /** 历史事件数量限制 */
    historyLimit?: number;
}

/** 订阅回调 */
export type EventCallback = (event: BaseEvent) => void | Promise<void>;

/** 订阅句柄 */
export interface Subscription {
    /** 订阅 ID */
    id: string;
    /** 取消订阅 */
    unsubscribe: () => void;
}

/** EventStream 配置 */
export interface EventStreamConfig {
    /** 最大保留事件数 */
    maxEvents?: number;
    /** 事件保留时间 (ms) */
    eventTTL?: number;
    /** 是否启用持久化 */
    enablePersistence?: boolean;
    /** 自动裁剪间隔 (ms) */
    pruneInterval?: number;
}

/**
 * 统一事件流处理器
 */
export class EventStream {
    private emitter: EventEmitter;
    private events: BaseEvent[] = [];
    private subscriptions: Map<string, { callback: EventCallback; filter?: EventFilter }> = new Map();
    private config: Required<EventStreamConfig>;
    private pruneTimer?: ReturnType<typeof setInterval>;
    private eventCounter: number = 0;

    constructor(config: EventStreamConfig = {}) {
        this.emitter = new EventEmitter();
        this.emitter.setMaxListeners(100);

        this.config = {
            maxEvents: config.maxEvents ?? 10000,
            eventTTL: config.eventTTL ?? 3600000, // 1小时
            enablePersistence: config.enablePersistence ?? false,
            pruneInterval: config.pruneInterval ?? 60000, // 1分钟
        };

        // 启动自动裁剪
        this.startPruning();
    }

    /**
     * 发布事件
     */
    emit(type: EventType, source: string, data: Record<string, unknown>, options?: {
        taskId?: string;
        traceId?: string;
    }): BaseEvent {
        const event: BaseEvent = {
            id: this.generateEventId(),
            type,
            timestamp: Date.now(),
            source,
            taskId: options?.taskId,
            traceId: options?.traceId,
            data,
        };

        // 存储事件
        this.events.push(event);
        this.pruneIfNeeded();

        // 通知订阅者
        this.notifySubscribers(event);

        return event;
    }

    /**
     * 订阅事件
     */
    subscribe(callback: EventCallback, options: SubscriptionOptions = {}): Subscription {
        const subscriptionId = `sub_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

        this.subscriptions.set(subscriptionId, {
            callback,
            filter: options.filter,
        });

        // 如果需要历史事件
        if (options.includeHistory) {
            const historyEvents = this.query(options.filter ?? {})
                .slice(-(options.historyLimit ?? 100));

            for (const event of historyEvents) {
                this.safeCallback(callback, event);
            }
        }

        return {
            id: subscriptionId,
            unsubscribe: () => {
                this.subscriptions.delete(subscriptionId);
            },
        };
    }

    /**
     * 查询历史事件
     */
    query(filter: EventFilter): BaseEvent[] {
        return this.events.filter(event => this.matchFilter(event, filter));
    }

    /**
     * 按任务 ID 查询事件
     */
    queryByTask(taskId: string): BaseEvent[] {
        return this.query({ taskId });
    }

    /**
     * 按时间范围查询
     */
    queryByTimeRange(startTime: number, endTime: number): BaseEvent[] {
        return this.query({ startTime, endTime });
    }

    /**
     * 获取最近 N 个事件
     */
    getRecent(count: number = 100): BaseEvent[] {
        return this.events.slice(-count);
    }

    /**
     * 获取事件统计
     */
    getStats(): {
        totalEvents: number;
        eventsByType: Record<string, number>;
        oldestEvent: number | null;
        newestEvent: number | null;
    } {
        const eventsByType: Record<string, number> = {};

        for (const event of this.events) {
            eventsByType[event.type] = (eventsByType[event.type] ?? 0) + 1;
        }

        return {
            totalEvents: this.events.length,
            eventsByType,
            oldestEvent: this.events.length > 0 ? this.events[0].timestamp : null,
            newestEvent: this.events.length > 0 ? this.events[this.events.length - 1].timestamp : null,
        };
    }

    /**
     * 清空事件
     */
    clear(): void {
        this.events = [];
    }

    /**
     * 销毁
     */
    destroy(): void {
        if (this.pruneTimer) {
            clearInterval(this.pruneTimer);
        }
        this.subscriptions.clear();
        this.events = [];
        this.emitter.removeAllListeners();
    }

    // ============ 便捷方法 ============

    /** 发布任务开始事件 */
    emitTaskStart(source: string, taskId: string, data: Record<string, unknown>): BaseEvent {
        return this.emit(EventType.TASK_START, source, data, { taskId });
    }

    /** 发布任务进度事件 */
    emitTaskProgress(source: string, taskId: string, data: Record<string, unknown>): BaseEvent {
        return this.emit(EventType.TASK_PROGRESS, source, data, { taskId });
    }

    /** 发布任务完成事件 */
    emitTaskComplete(source: string, taskId: string, data: Record<string, unknown>): BaseEvent {
        return this.emit(EventType.TASK_COMPLETE, source, data, { taskId });
    }

    /** 发布任务错误事件 */
    emitTaskError(source: string, taskId: string, data: Record<string, unknown>): BaseEvent {
        return this.emit(EventType.TASK_ERROR, source, data, { taskId });
    }

    /** 发布工具调用事件 */
    emitToolCall(source: string, data: Record<string, unknown>, taskId?: string): BaseEvent {
        return this.emit(EventType.TOOL_CALL, source, data, { taskId });
    }

    /** 发布工具结果事件 */
    emitToolResult(source: string, data: Record<string, unknown>, taskId?: string): BaseEvent {
        return this.emit(EventType.TOOL_RESULT, source, data, { taskId });
    }

    /** 发布 LLM 请求事件 */
    emitLLMRequest(source: string, data: Record<string, unknown>, taskId?: string): BaseEvent {
        return this.emit(EventType.LLM_REQUEST, source, data, { taskId });
    }

    /** 发布 LLM 响应事件 */
    emitLLMResponse(source: string, data: Record<string, unknown>, taskId?: string): BaseEvent {
        return this.emit(EventType.LLM_RESPONSE, source, data, { taskId });
    }

    /** 发布 LLM 流式块事件 */
    emitLLMStreamChunk(source: string, data: Record<string, unknown>, taskId?: string): BaseEvent {
        return this.emit(EventType.LLM_STREAM_CHUNK, source, data, { taskId });
    }

    // ============ 私有方法 ============

    private generateEventId(): string {
        return `evt_${Date.now()}_${(this.eventCounter++).toString(36)}`;
    }

    private matchFilter(event: BaseEvent, filter: EventFilter): boolean {
        if (filter.types && filter.types.length > 0 && !filter.types.includes(event.type)) {
            return false;
        }
        if (filter.taskId && event.taskId !== filter.taskId) {
            return false;
        }
        if (filter.source && event.source !== filter.source) {
            return false;
        }
        if (filter.startTime && event.timestamp < filter.startTime) {
            return false;
        }
        if (filter.endTime && event.timestamp > filter.endTime) {
            return false;
        }
        return true;
    }

    private notifySubscribers(event: BaseEvent): void {
        for (const [, subscription] of this.subscriptions) {
            if (!subscription.filter || this.matchFilter(event, subscription.filter)) {
                this.safeCallback(subscription.callback, event);
            }
        }
    }

    private safeCallback(callback: EventCallback, event: BaseEvent): void {
        try {
            const result = callback(event);
            if (result instanceof Promise) {
                result.catch(err => {
                    console.error('[EventStream] Callback error:', err);
                });
            }
        } catch (err) {
            console.error('[EventStream] Callback error:', err);
        }
    }

    private pruneIfNeeded(): void {
        // 按数量裁剪
        if (this.events.length > this.config.maxEvents) {
            this.events = this.events.slice(-this.config.maxEvents);
        }
    }

    private startPruning(): void {
        this.pruneTimer = setInterval(() => {
            const cutoff = Date.now() - this.config.eventTTL;
            this.events = this.events.filter(e => e.timestamp > cutoff);
        }, this.config.pruneInterval);
    }
}

/** 全局事件流实例 */
let globalEventStream: EventStream | null = null;

/**
 * 获取全局事件流实例
 */
export function getEventStream(): EventStream {
    if (!globalEventStream) {
        globalEventStream = new EventStream();
    }
    return globalEventStream;
}

/**
 * 设置全局事件流实例
 */
export function setEventStream(stream: EventStream): void {
    globalEventStream = stream;
}
