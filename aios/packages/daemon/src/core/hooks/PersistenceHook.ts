/**
 * PersistenceHook - 持久化 Hook
 * 将任务和消息自动保存到 SessionManager
 */

import { BaseHook } from './BaseHook.js';
import { HookPriority } from './types.js';
import type {
    TaskStartEvent,
    TaskCompleteEvent,
    TaskErrorEvent,
    TaskProgress,
    ToolCallInfo,
    ToolResultInfo,
} from './types.js';
import type { SessionManager } from '../storage/index.js';

/**
 * 持久化 Hook 配置
 */
export interface PersistenceHookConfig {
    /** 会话管理器 */
    sessionManager: SessionManager;
    /** 是否保存工具调用 */
    saveToolCalls?: boolean;
}

/**
 * 持久化 Hook
 * 自动将任务生命周期事件保存到数据库
 */
export class PersistenceHook extends BaseHook {
    private sessionManager: SessionManager;
    private saveToolCalls: boolean;
    private taskIdToDbTaskId: Map<string, string> = new Map();

    constructor(config: PersistenceHookConfig) {
        super('PersistenceHook', { priority: HookPriority.HIGH });
        this.sessionManager = config.sessionManager;
        this.saveToolCalls = config.saveToolCalls ?? true;
    }

    /**
     * 任务开始时创建数据库记录
     */
    async onTaskStart(event: TaskStartEvent): Promise<void> {
        try {
            // 创建任务记录
            const dbTask = this.sessionManager.createTask(
                event.input,
                event.analysis?.taskType || 'simple'
            );

            // 保存映射
            this.taskIdToDbTaskId.set(event.taskId, dbTask.id);

            console.log(`[PersistenceHook] Task ${event.taskId} persisted as ${dbTask.id}`);
        } catch (error) {
            console.error('[PersistenceHook] Failed to persist task start:', error);
        }
    }

    /**
     * 任务完成时更新记录
     */
    async onTaskComplete(event: TaskCompleteEvent): Promise<void> {
        try {
            const dbTaskId = this.taskIdToDbTaskId.get(event.taskId);
            if (!dbTaskId) return;

            // 更新任务状态
            this.sessionManager.updateTaskStatus(dbTaskId, 'completed', {
                response: event.result.response,
                executionTime: event.duration,
            });

            // 清理映射
            this.taskIdToDbTaskId.delete(event.taskId);

            console.log(`[PersistenceHook] Task ${event.taskId} completed and persisted`);
        } catch (error) {
            console.error('[PersistenceHook] Failed to persist task complete:', error);
        }
    }

    /**
     * 任务错误时记录
     */
    async onTaskError(event: TaskErrorEvent): Promise<void> {
        try {
            const dbTaskId = this.taskIdToDbTaskId.get(event.taskId);
            if (!dbTaskId) return;

            // 更新任务状态为失败
            this.sessionManager.updateTaskStatus(dbTaskId, 'failed', {
                error: event.error.message,
            });

            // 清理映射
            this.taskIdToDbTaskId.delete(event.taskId);

            console.log(`[PersistenceHook] Task ${event.taskId} error persisted`);
        } catch (error) {
            console.error('[PersistenceHook] Failed to persist task error:', error);
        }
    }

    /**
     * 工具调用时记录
     */
    async onToolCall(info: ToolCallInfo): Promise<void> {
        if (!this.saveToolCalls) return;
        console.log(`[PersistenceHook] Tool call: ${info.adapterId}.${info.capabilityId}`);
    }

    /**
     * 工具结果时记录
     */
    async onToolResult(info: ToolResultInfo): Promise<void> {
        if (!this.saveToolCalls) return;
        console.log(`[PersistenceHook] Tool result: ${info.adapterId}.${info.capabilityId}, success: ${info.success}`);
    }
}
