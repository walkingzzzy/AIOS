/**
 * TaskAPI - 任务管理 JSON-RPC API
 * 提供任务提交、取消、状态查询等接口
 */

import type { JSONRPCHandler } from '../core/JSONRPCHandler.js';
import {
    TaskScheduler,
    TaskPriority,
    TaskStatus,
    type Task,
    type QueueStats,
    type TaskSubmitOptions,
} from '../core/scheduler/index.js';
import {
    SessionManager,
    type TaskRecord,
    type PaginatedResult,
} from '../core/storage/index.js';

/**
 * 任务提交参数
 */
export interface TaskSubmitParams {
    /** 用户输入/提示 */
    prompt: string;
    /** 优先级 */
    priority?: 'critical' | 'high' | 'normal' | 'low' | 'background';
    /** 任务类型 */
    type?: 'simple' | 'visual' | 'complex';
    /** 超时时间 (ms) */
    timeout?: number;
    /** 元数据 */
    metadata?: Record<string, unknown>;
}

/**
 * 任务取消参数
 */
export interface TaskCancelParams {
    /** 任务 ID */
    taskId: string;
}

/**
 * 任务状态查询参数
 */
export interface TaskStatusParams {
    /** 任务 ID */
    taskId: string;
}

/**
 * 任务历史查询参数
 */
export interface TaskHistoryParams {
    /** 会话 ID */
    sessionId?: string;
    /** 状态过滤 */
    status?: string;
    /** 页码 */
    page?: number;
    /** 每页数量 */
    pageSize?: number;
}

/**
 * 任务提交结果
 */
export interface TaskSubmitResult {
    /** 任务 ID */
    taskId: string;
    /** 任务状态 */
    status: string;
    /** 队列位置 */
    position: number;
}

/**
 * 任务状态结果
 */
export interface TaskStatusResult {
    /** 任务 ID */
    taskId: string;
    /** 任务状态 */
    status: string;
    /** 提示 */
    prompt: string;
    /** 创建时间 */
    createdAt: number;
    /** 开始时间 */
    startedAt?: number;
    /** 完成时间 */
    completedAt?: number;
    /** 执行时间 (ms) */
    executionTime?: number;
    /** 响应 */
    response?: string;
    /** 错误信息 */
    error?: string;
}

/**
 * 队列状态结果
 */
export interface QueueStatusResult extends QueueStats {
    /** 队列中的任务列表 */
    tasks: Array<{
        taskId: string;
        status: string;
        prompt: string;
        priority: number;
    }>;
}

/**
 * 优先级映射
 */
const PRIORITY_MAP: Record<string, TaskPriority> = {
    critical: TaskPriority.CRITICAL,
    high: TaskPriority.HIGH,
    normal: TaskPriority.NORMAL,
    low: TaskPriority.LOW,
    background: TaskPriority.BACKGROUND,
};

/**
 * 任务 API
 */
export class TaskAPI {
    private scheduler: TaskScheduler<unknown>;
    private sessionManager: SessionManager;

    constructor(scheduler: TaskScheduler<unknown>, sessionManager: SessionManager) {
        this.scheduler = scheduler;
        this.sessionManager = sessionManager;
    }

    /**
     * 注册所有任务相关的 JSON-RPC 方法
     */
    registerMethods(handler: JSONRPCHandler): void {
        handler.registerMethod('task.submit', (params) => this.submit(params as unknown as TaskSubmitParams));
        handler.registerMethod('task.cancel', (params) => this.cancel(params as unknown as TaskCancelParams));
        handler.registerMethod('task.getStatus', (params) => this.getStatus(params as unknown as TaskStatusParams));
        handler.registerMethod('task.getQueue', () => this.getQueue());
        handler.registerMethod('task.getHistory', (params) => this.getHistory(params as unknown as TaskHistoryParams));
    }

    /**
     * 提交任务
     */
    async submit(params: TaskSubmitParams): Promise<TaskSubmitResult> {
        if (!params.prompt || typeof params.prompt !== 'string') {
            throw new Error('参数 prompt 必须是非空字符串');
        }

        // 映射优先级
        const priority = params.priority ? PRIORITY_MAP[params.priority] ?? TaskPriority.NORMAL : TaskPriority.NORMAL;

        // 先创建持久化记录（使用其 ID 作为调度器任务 ID，保证全链路一致）
        const dbTask = this.sessionManager.createTask(
            params.prompt,
            params.type ?? 'simple',
            params.metadata
        );

        // 提交到调度器
        const options: TaskSubmitOptions = {
            id: dbTask.id,
            priority,
            type: params.type,
            timeout: params.timeout,
            metadata: params.metadata,
        };

        const task = await this.scheduler.submit(params.prompt, options);

        // 计算队列位置
        const queue = this.scheduler.getQueue();
        const position = queue.findIndex(t => t.id === task.id) + 1;

        return {
            taskId: task.id,
            status: task.status,
            position: position > 0 ? position : queue.length + 1,
        };
    }

    /**
     * 取消任务
     */
    async cancel(params: TaskCancelParams): Promise<{ success: boolean; message: string }> {
        if (!params.taskId) {
            throw new Error('参数 taskId 必须提供');
        }

        const cancelled = this.scheduler.cancel(params.taskId);

        if (cancelled) {
            // 更新持久化状态
            this.sessionManager.updateTaskStatus(params.taskId, 'cancelled');
            return { success: true, message: '任务已取消' };
        } else {
            return { success: false, message: '无法取消任务（可能正在执行或已完成）' };
        }
    }

    /**
     * 获取任务状态
     */
    async getStatus(params: TaskStatusParams): Promise<TaskStatusResult | null> {
        if (!params.taskId) {
            throw new Error('参数 taskId 必须提供');
        }

        // 优先从调度器获取（实时状态）
        const schedulerTask = this.scheduler.getTask(params.taskId);
        if (schedulerTask) {
            return {
                taskId: schedulerTask.id,
                status: schedulerTask.status,
                prompt: schedulerTask.prompt,
                createdAt: schedulerTask.createdAt,
                startedAt: schedulerTask.startedAt,
                completedAt: schedulerTask.completedAt,
                error: schedulerTask.error?.message,
            };
        }

        // 从持久化存储获取
        const storedTask = this.sessionManager.getTask(params.taskId);
        if (storedTask) {
            return {
                taskId: storedTask.id,
                status: storedTask.status,
                prompt: storedTask.prompt,
                createdAt: storedTask.createdAt,
                startedAt: storedTask.startedAt,
                completedAt: storedTask.completedAt,
                executionTime: storedTask.executionTime,
                response: storedTask.response,
                error: storedTask.error,
            };
        }

        return null;
    }

    /**
     * 获取队列状态
     */
    async getQueue(): Promise<QueueStatusResult> {
        const stats = this.scheduler.getStats();
        const queue = this.scheduler.getQueue();

        return {
            ...stats,
            tasks: queue.map(task => ({
                taskId: task.id,
                status: task.status,
                prompt: task.prompt.substring(0, 100) + (task.prompt.length > 100 ? '...' : ''),
                priority: task.priority,
            })),
        };
    }

    /**
     * 获取任务历史
     */
    async getHistory(params: TaskHistoryParams = {}): Promise<PaginatedResult<TaskRecord>> {
        return this.sessionManager.queryTasks({
            sessionId: params.sessionId,
            status: params.status as any,
            page: params.page,
            pageSize: params.pageSize ?? 20,
        });
    }
}
