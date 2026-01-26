/**
 * EventBridgeHook - Hook 事件桥接到 EventStream
 * 将 HookManager 中的事件同步发布到 EventStream，实现统一可观测性
 */

import { BaseHook } from './BaseHook.js';
import { HookPriority } from './types.js';
import type {
    TaskStartEvent,
    TaskCompleteEvent,
    TaskErrorEvent,
    TaskProgress,
    LLMRequestEvent,
    LLMResponseEvent,
    LLMStreamChunkEvent,
    ToolCallInfo,
    ToolResultInfo,
} from './types.js';
import type { EventStream } from '../events/EventStream.js';
import { EventType } from '../events/EventStream.js';

/**
 * EventBridge 配置
 */
export interface EventBridgeConfig {
    /** 是否桥接任务事件 */
    bridgeTaskEvents?: boolean;
    /** 是否桥接 LLM 事件 */
    bridgeLLMEvents?: boolean;
    /** 是否桥接工具事件 */
    bridgeToolEvents?: boolean;
    /** 是否桥接进度事件 */
    bridgeProgressEvents?: boolean;
}

/**
 * EventBridgeHook - 将 Hook 事件桥接到 EventStream
 */
export class EventBridgeHook extends BaseHook {
    private eventStream: EventStream;
    private config: Required<EventBridgeConfig>;

    constructor(eventStream: EventStream, config: EventBridgeConfig = {}) {
        super('event-bridge', {
            description: '将 Hook 事件转发到统一事件流',
            priority: HookPriority.LOWEST, // 最低优先级，最后执行
        });

        this.eventStream = eventStream;
        this.config = {
            bridgeTaskEvents: config.bridgeTaskEvents ?? true,
            bridgeLLMEvents: config.bridgeLLMEvents ?? true,
            bridgeToolEvents: config.bridgeToolEvents ?? true,
            bridgeProgressEvents: config.bridgeProgressEvents ?? true,
        };
    }

    // ============ 任务生命周期事件 ============

    /**
     * 任务开始
     */
    async onTaskStart(event: TaskStartEvent): Promise<void> {
        if (!this.config.bridgeTaskEvents) return;

        this.eventStream.emitTaskStart('HookBridge', event.taskId, {
            input: event.input,
            analysis: event.analysis,
            timestamp: event.timestamp,
        });
    }

    /**
     * 任务进度
     */
    async onProgress(progress: TaskProgress): Promise<void> {
        if (!this.config.bridgeProgressEvents) return;

        this.eventStream.emitTaskProgress('HookBridge', progress.taskId, {
            currentStep: progress.currentStep,
            totalSteps: progress.totalSteps,
            percentage: progress.percentage,
            stepDescription: progress.stepDescription,
            metadata: progress.metadata,
        });
    }

    /**
     * 任务完成
     */
    async onTaskComplete(event: TaskCompleteEvent): Promise<void> {
        if (!this.config.bridgeTaskEvents) return;

        this.eventStream.emitTaskComplete('HookBridge', event.taskId, {
            result: event.result,
            duration: event.duration,
            sessionId: event.sessionId,
            traceId: event.traceId,
        });
    }

    /**
     * 任务错误
     */
    async onTaskError(event: TaskErrorEvent): Promise<void> {
        if (!this.config.bridgeTaskEvents) return;

        this.eventStream.emitTaskError('HookBridge', event.taskId, {
            error: event.error.message,
            recoverable: event.recoverable,
            timestamp: event.timestamp,
        });
    }

    // ============ LLM 生命周期事件 ============

    /**
     * LLM 请求
     */
    async onLLMRequest(event: LLMRequestEvent): Promise<void> {
        if (!this.config.bridgeLLMEvents) return;

        this.eventStream.emit(EventType.LLM_REQUEST, 'HookBridge', {
            requestId: event.requestId,
            engineId: event.engineId,
            model: event.model,
            messageCount: event.messages.length,
            toolCount: event.tools?.length ?? 0,
            isStream: event.options?.stream ?? false,
        }, { taskId: event.taskId });
    }

    /**
     * LLM 响应
     */
    async onLLMResponse(event: LLMResponseEvent): Promise<void> {
        if (!this.config.bridgeLLMEvents) return;

        this.eventStream.emit(EventType.LLM_RESPONSE, 'HookBridge', {
            requestId: event.requestId,
            engineId: event.engineId,
            model: event.model,
            contentLength: event.content.length,
            finishReason: event.finishReason,
            toolCallCount: event.toolCalls?.length ?? 0,
            usage: event.usage,
            latency: event.latency,
        }, { taskId: event.taskId });
    }

    /**
     * LLM 流式块
     */
    async onLLMStreamChunk(event: LLMStreamChunkEvent): Promise<void> {
        if (!this.config.bridgeLLMEvents) return;

        // 仅在完成时发布事件，避免过多事件
        if (event.finished) {
            this.eventStream.emit(EventType.LLM_STREAM_CHUNK, 'HookBridge', {
                requestId: event.requestId,
                engineId: event.engineId,
                chunkIndex: event.chunkIndex,
                finished: event.finished,
                finishReason: event.finishReason,
            }, { taskId: event.taskId });
        }
    }

    // ============ 工具事件 ============

    /**
     * 工具调用开始
     */
    async onToolCall(info: ToolCallInfo): Promise<void> {
        if (!this.config.bridgeToolEvents) return;

        this.eventStream.emitToolCall('HookBridge', {
            toolId: info.toolId,
            adapterId: info.adapterId,
            capabilityId: info.capabilityId,
            timestamp: info.timestamp,
            sessionId: info.sessionId,
            traceId: info.traceId,
        }, info.taskId);
    }

    /**
     * 工具执行结果
     */
    async onToolResult(info: ToolResultInfo): Promise<void> {
        if (!this.config.bridgeToolEvents) return;

        this.eventStream.emitToolResult('HookBridge', {
            toolId: info.toolId,
            adapterId: info.adapterId,
            capabilityId: info.capabilityId,
            success: info.success,
            duration: info.duration,
            traceId: info.traceId,
        }, info.taskId);
    }
}
