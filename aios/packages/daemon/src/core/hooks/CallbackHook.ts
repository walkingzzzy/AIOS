/**
 * CallbackHook - 回调通知 Hook
 * 支持向外部系统（如 Electron IPC）推送事件
 */

import { BaseHook } from './BaseHook.js';
import {
    HookPriority,
    type TaskStartEvent,
    type TaskProgress,
    type ToolCallInfo,
    type ToolResultInfo,
    type TaskCompleteEvent,
    type TaskErrorEvent,
} from './types.js';

/**
 * 回调事件类型
 */
export type CallbackEventType =
    | 'task:start'
    | 'task:progress'
    | 'task:complete'
    | 'task:error'
    | 'tool:call'
    | 'tool:result';

/**
 * 回调事件
 */
export interface CallbackEvent {
    type: CallbackEventType;
    taskId: string;
    timestamp: number;
    data: unknown;
}

/**
 * 回调处理器
 */
export type CallbackHandler = (event: CallbackEvent) => void | Promise<void>;

/**
 * 回调通知 Hook
 */
export class CallbackHook extends BaseHook {
    /** 回调处理器 */
    private handler: CallbackHandler;

    /** 事件过滤器（哪些事件需要回调） */
    private eventFilter: Set<CallbackEventType>;

    constructor(
        handler: CallbackHandler,
        options: {
            events?: CallbackEventType[];
        } = {}
    ) {
        super('CallbackHook', {
            description: '向外部系统推送事件回调',
            priority: HookPriority.LOW, // 低优先级，在其他处理完成后回调
        });
        this.handler = handler;
        this.eventFilter = new Set(options.events ?? [
            'task:start',
            'task:progress',
            'task:complete',
            'task:error',
        ]);
    }

    private async emit(type: CallbackEventType, taskId: string, data: unknown): Promise<void> {
        if (!this.eventFilter.has(type)) {
            return;
        }

        const event: CallbackEvent = {
            type,
            taskId,
            timestamp: Date.now(),
            data,
        };

        try {
            await this.handler(event);
        } catch (error) {
            console.error('[CallbackHook] Handler error:', error);
        }
    }

    async onTaskStart(event: TaskStartEvent): Promise<void> {
        await this.emit('task:start', event.taskId, {
            input: event.input,
            analysis: event.analysis,
        });
    }

    async onProgress(progress: TaskProgress): Promise<void> {
        await this.emit('task:progress', progress.taskId, {
            currentStep: progress.currentStep,
            totalSteps: progress.totalSteps,
            percentage: progress.percentage,
            stepDescription: progress.stepDescription,
        });
    }

    async onToolCall(info: ToolCallInfo): Promise<void> {
        await this.emit('tool:call', info.toolId, {
            adapterId: info.adapterId,
            capabilityId: info.capabilityId,
            params: info.params,
        });
    }

    async onToolResult(info: ToolResultInfo): Promise<void> {
        await this.emit('tool:result', info.toolId, {
            adapterId: info.adapterId,
            capabilityId: info.capabilityId,
            success: info.success,
            duration: info.duration,
            error: info.error?.message,
        });
    }

    async onTaskComplete(event: TaskCompleteEvent): Promise<void> {
        await this.emit('task:complete', event.taskId, {
            success: event.result.success,
            response: event.result.response,
            duration: event.duration,
        });
    }

    async onTaskError(event: TaskErrorEvent): Promise<void> {
        await this.emit('task:error', event.taskId, {
            error: event.error.message,
            stack: event.error.stack,
            recoverable: event.recoverable,
        });
    }

    /**
     * 更新事件过滤器
     */
    setEventFilter(events: CallbackEventType[]): void {
        this.eventFilter = new Set(events);
    }
}
