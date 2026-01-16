/**
 * ProgressAPI - 进度推送 API
 * 提供实时进度事件推送
 */

import {
    CallbackHook,
    type CallbackHandler,
    type CallbackEvent,
    type CallbackEventType,
} from '../core/hooks/index.js';

/**
 * 进度事件订阅者
 */
export type ProgressSubscriber = (event: ProgressEvent) => void;

/**
 * 进度事件
 */
export interface ProgressEvent {
    /** 事件类型 */
    type: string;
    /** 任务 ID */
    taskId: string;
    /** 时间戳 */
    timestamp: number;
    /** 事件数据 */
    data: Record<string, unknown>;
}

/**
 * 进度 API
 * 管理进度事件的订阅和推送
 */
export class ProgressAPI {
    /** 订阅者列表 */
    private subscribers: Set<ProgressSubscriber> = new Set();

    /** 回调 Hook */
    private callbackHook: CallbackHook;

    constructor() {
        // 创建回调处理器
        const handler: CallbackHandler = (event: CallbackEvent) => {
            this.broadcast(this.convertEvent(event));
        };

        this.callbackHook = new CallbackHook(handler, {
            events: [
                'task:start',
                'task:progress',
                'task:complete',
                'task:error',
                'tool:call',
                'tool:result',
            ],
        });
    }

    /**
     * 获取 CallbackHook（用于注册到 HookManager）
     */
    getHook(): CallbackHook {
        return this.callbackHook;
    }

    /**
     * 订阅进度事件
     */
    subscribe(subscriber: ProgressSubscriber): () => void {
        this.subscribers.add(subscriber);
        console.log(`[ProgressAPI] Subscriber added, total: ${this.subscribers.size}`);

        // 返回取消订阅函数
        return () => {
            this.subscribers.delete(subscriber);
            console.log(`[ProgressAPI] Subscriber removed, total: ${this.subscribers.size}`);
        };
    }

    /**
     * 广播事件给所有订阅者
     */
    private broadcast(event: ProgressEvent): void {
        for (const subscriber of this.subscribers) {
            try {
                subscriber(event);
            } catch (error) {
                console.error('[ProgressAPI] Subscriber error:', error);
            }
        }
    }

    /**
     * 转换 CallbackEvent 为 ProgressEvent
     */
    private convertEvent(event: CallbackEvent): ProgressEvent {
        return {
            type: event.type,
            taskId: event.taskId,
            timestamp: event.timestamp,
            data: event.data as Record<string, unknown>,
        };
    }

    /**
     * 手动推送进度事件
     */
    emit(type: string, taskId: string, data: Record<string, unknown>): void {
        const event: ProgressEvent = {
            type,
            taskId,
            timestamp: Date.now(),
            data,
        };
        this.broadcast(event);
    }

    /**
     * 手动推送任务进度
     */
    emitProgress(
        taskId: string,
        currentStep: number,
        totalSteps: number,
        description?: string
    ): void {
        this.emit('task:progress', taskId, {
            currentStep,
            totalSteps,
            percentage: Math.round((currentStep / totalSteps) * 100),
            description,
        });
    }

    /**
     * 获取订阅者数量
     */
    get subscriberCount(): number {
        return this.subscribers.size;
    }

    /**
     * 清除所有订阅者
     */
    clear(): void {
        this.subscribers.clear();
    }
}
