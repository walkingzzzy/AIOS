/**
 * ToolTraceHook - 工具追踪 Hook
 * 捕获每次适配器调用并持久化
 */

import { BaseHook } from '../hooks/BaseHook.js';
import { HookPriority, type ToolCallInfo, type ToolResultInfo } from '../hooks/types.js';
import { ToolTraceRepository } from './ToolTraceRepository.js';
import type { ToolTraceHookConfig } from './types.js';

/**
 * 工具追踪 Hook
 */
export class ToolTraceHook extends BaseHook {
    private repository: ToolTraceRepository;
    private config: Required<ToolTraceHookConfig>;

    /** 活跃的追踪（用于合并乱序事件） */
    private activeTraces: Map<string, { sessionId: string; taskId: string; startedAt: number }>;

    constructor(
        repository: ToolTraceRepository,
        config: ToolTraceHookConfig = {}
    ) {
        super('ToolTraceHook', {
            description: '追踪工具调用并持久化',
            priority: HookPriority.LOW, // 低优先级，不阻塞主流程
        });

        this.repository = repository;
        this.config = {
            enabled: config.enabled ?? true,
            logInput: config.logInput ?? true,
            logOutput: config.logOutput ?? true,
            maxInputLength: config.maxInputLength ?? 10000,
            maxOutputLength: config.maxOutputLength ?? 10000,
        };
        this.activeTraces = new Map();
    }

    /**
     * 工具调用开始
     */
    async onToolCall(info: ToolCallInfo): Promise<void> {
        if (!this.config.enabled) return;

        try {
            // 记录活跃追踪
            this.activeTraces.set(info.toolId, {
                sessionId: info.sessionId ?? 'unknown',
                taskId: info.taskId ?? 'unknown',
                startedAt: Date.now(),
            });

            // 处理输入参数
            let input: Record<string, unknown> = (info.params ?? {}) as Record<string, unknown>;
            if (this.config.logInput) {
                input = this.truncateObject(input, this.config.maxInputLength) as Record<string, unknown>;
            } else {
                input = { _redacted: true };
            }

            // 创建待处理记录
            this.repository.createPending({
                toolUseId: info.toolId,
                sessionId: info.sessionId ?? 'unknown',
                taskId: info.taskId ?? 'unknown',
                adapterId: info.adapterId,
                capabilityId: info.capabilityId,
                input,
                startedAt: Date.now(),
                traceId: info.traceId,
            });
        } catch (error) {
            console.error('[ToolTraceHook] Failed to record tool call:', error);
        }
    }

    /**
     * 工具调用结束
     */
    async onToolResult(info: ToolResultInfo): Promise<void> {
        if (!this.config.enabled) return;

        try {
            const activeTrace = this.activeTraces.get(info.toolId);
            const duration = info.duration ?? (activeTrace ? Date.now() - activeTrace.startedAt : 0);

            // 清理活跃追踪
            this.activeTraces.delete(info.toolId);

            if (info.success) {
                // 处理输出结果
                let output = info.result;
                if (this.config.logOutput && output !== undefined) {
                    output = this.truncateObject(output, this.config.maxOutputLength);
                } else if (!this.config.logOutput) {
                    output = { _redacted: true };
                }

                this.repository.complete(info.toolId, output, duration);
            } else {
                const errorMessage = info.error?.message ?? 'Unknown error';
                this.repository.fail(info.toolId, errorMessage, duration);
            }
        } catch (error) {
            console.error('[ToolTraceHook] Failed to record tool result:', error);
        }
    }

    /**
     * 截断对象以控制存储大小
     */
    private truncateObject(obj: unknown, maxLength: number): unknown {
        const str = JSON.stringify(obj);
        if (str.length <= maxLength) {
            return obj;
        }

        // 截断并标记
        return {
            _truncated: true,
            _originalLength: str.length,
            _preview: str.substring(0, maxLength - 100) + '...',
        };
    }

    /**
     * 获取统计信息
     */
    getStats(options?: { sessionId?: string; taskId?: string }) {
        return this.repository.getStats(options);
    }

    /**
     * 清理过期记录
     */
    cleanup(): number {
        return this.repository.cleanup();
    }

    /**
     * 设置配置
     */
    setConfig(config: Partial<ToolTraceHookConfig>): void {
        Object.assign(this.config, config);
    }

    /**
     * 获取配置
     */
    getConfig(): Required<ToolTraceHookConfig> {
        return { ...this.config };
    }
}
