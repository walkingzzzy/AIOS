/**
 * TaskScheduler - 任务调度器
 * 基于 p-queue 实现任务队列、并发控制和优先级调度
 */

import PQueue from 'p-queue';
import {
    TaskPriority,
    TaskStatus,
    type Task,
    type TaskType,
    type TaskSubmitOptions,
    type TaskExecutor,
    type QueueStats,
} from './types.js';

/**
 * 调度器配置
 */
export interface TaskSchedulerConfig {
    /** 并发数 */
    concurrency?: number;
    /** 默认超时时间 (ms) */
    defaultTimeout?: number;
    /** 是否自动启动 */
    autoStart?: boolean;
    /** 队列间隔 (ms) */
    interval?: number;
    /** 每个间隔最大任务数 */
    intervalCap?: number;
}

/**
 * 事件监听器类型
 */
type EventListener<T extends (...args: unknown[]) => void> = T;

/**
 * 任务调度器
 */
export class TaskScheduler<TResult = unknown> {
    /** 内部队列 */
    private queue: PQueue;

    /** 任务存储 */
    private tasks: Map<string, Task<TResult>> = new Map();

    /** 任务执行器 */
    private executor: TaskExecutor<TResult>;

    /** 默认超时时间 */
    private defaultTimeout: number;

    /** 统计信息 */
    private stats = {
        completed: 0,
        failed: 0,
        total: 0,
    };

    /** 事件监听器 */
    private listeners: Map<string, Set<EventListener<(...args: unknown[]) => void>>> = new Map();

    constructor(executor: TaskExecutor<TResult>, config: TaskSchedulerConfig = {}) {
        this.executor = executor;
        this.defaultTimeout = config.defaultTimeout ?? 60000; // 默认 60 秒

        // 构建 p-queue 配置，只传递已定义的选项
        const queueOptions: {
            concurrency: number;
            autoStart: boolean;
            interval?: number;
            intervalCap?: number;
        } = {
            concurrency: config.concurrency ?? 3,
            autoStart: config.autoStart ?? true,
        };

        // 只在有 interval 时才设置 intervalCap
        if (config.interval !== undefined) {
            queueOptions.interval = config.interval;
            queueOptions.intervalCap = config.intervalCap ?? 1;
        }

        this.queue = new PQueue(queueOptions);

        // 监听队列事件
        this.queue.on('idle', () => this.emit('queue:idle'));
        this.queue.on('active', () => this.emit('queue:active'));
    }

    /**
     * 生成任务 ID
     */
    private generateId(): string {
        return `task_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * 提交任务
     */
    async submit(prompt: string, options: TaskSubmitOptions = {}): Promise<Task<TResult>> {
        const task: Task<TResult> = {
            id: options.id ?? this.generateId(),
            type: options.type ?? 'simple',
            priority: options.priority ?? TaskPriority.NORMAL,
            status: TaskStatus.PENDING,
            prompt,
            context: options.context,
            createdAt: Date.now(),
            timeout: options.timeout ?? this.defaultTimeout,
            maxRetries: options.maxRetries ?? 0,
            retryCount: 0,
            metadata: options.metadata,
        };

        this.tasks.set(task.id, task);
        this.stats.total++;
        this.emit('task:queued', task);

        console.log(`[TaskScheduler] Task queued: ${task.id} (priority: ${task.priority})`);

        // 添加到队列
        this.queue.add(
            () => this.executeTask(task),
            { priority: this.mapPriority(task.priority) }
        );

        return task;
    }

    /**
     * 映射优先级到 p-queue 优先级
     *
     * 注意：p-queue 是 “数字越大优先级越高”，而我们的 TaskPriority 是 “数字越小优先级越高”。
     */
    private mapPriority(priority: TaskPriority): number {
        return TaskPriority.BACKGROUND - priority;
    }

    /**
     * 执行任务
     */
    private async executeTask(task: Task<TResult>): Promise<void> {
        // 可能在进入执行前已被取消（例如：先 submit 后 cancel）
        if (task.status === TaskStatus.CANCELLED) {
            return;
        }

        task.status = TaskStatus.RUNNING;
        task.startedAt = Date.now();
        this.emit('task:started', task);

        console.log(`[TaskScheduler] Task started: ${task.id}`);

        try {
            // 带超时的执行
            const result = await this.executeWithTimeout(task);

            // 运行过程中如果被取消，保持 CANCELLED，不回跳到 COMPLETED
            // 使用 fresh 读取绕过 TypeScript 控制流分析
            const currentStatus = task.status as TaskStatus;
            if (currentStatus === TaskStatus.CANCELLED) {
                return;
            }

            task.status = TaskStatus.COMPLETED;
            task.result = result;
            task.completedAt = Date.now();
            this.stats.completed++;

            console.log(`[TaskScheduler] Task completed: ${task.id}`);
            this.emit('task:completed', task);
        } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));

            // 如果在执行/重试过程中被取消，不再继续处理
            // 使用 fresh 读取绕过 TypeScript 控制流分析
            const currentStatus = task.status as TaskStatus;
            if (currentStatus === TaskStatus.CANCELLED) {
                return;
            }

            // 检查是否需要重试
            if (task.retryCount! < task.maxRetries!) {
                task.retryCount!++;
                console.log(`[TaskScheduler] Task retry ${task.retryCount}/${task.maxRetries}: ${task.id}`);
                task.status = TaskStatus.PENDING;

                // 重新加入队列
                this.queue.add(
                    () => this.executeTask(task),
                    { priority: this.mapPriority(task.priority) }
                );
                return;
            }

            task.status = err.message.includes('timeout') ? TaskStatus.TIMEOUT : TaskStatus.FAILED;
            task.error = err;
            task.completedAt = Date.now();
            this.stats.failed++;

            console.error(`[TaskScheduler] Task failed: ${task.id}`, err.message);
            this.emit('task:failed', task, err);
        }
    }

    /**
     * 带超时的任务执行
     */
    private async executeWithTimeout(task: Task<TResult>): Promise<TResult> {
        const timeout = task.timeout ?? this.defaultTimeout;

        return Promise.race([
            this.executor(task),
            new Promise<never>((_, reject) =>
                setTimeout(() => reject(new Error(`Task timeout after ${timeout}ms`)), timeout)
            ),
        ]);
    }

    /**
     * 取消任务
     */
    cancel(taskId: string): boolean {
        const task = this.tasks.get(taskId);
        if (!task) {
            return false;
        }

        if (task.status === TaskStatus.PENDING) {
            task.status = TaskStatus.CANCELLED;
            task.completedAt = Date.now();
            this.emit('task:cancelled', task);
            console.log(`[TaskScheduler] Task cancelled: ${taskId}`);
            return true;
        }

        // 正在运行的任务无法直接取消
        if (task.status === TaskStatus.RUNNING) {
            console.warn(`[TaskScheduler] Cannot cancel running task: ${taskId}`);
            return false;
        }

        return false;
    }

    /**
     * 获取任务状态
     */
    getTask(taskId: string): Task<TResult> | undefined {
        return this.tasks.get(taskId);
    }

    /**
     * 获取任务状态
     */
    getStatus(taskId: string): TaskStatus | undefined {
        return this.tasks.get(taskId)?.status;
    }

    /**
     * 获取队列中的任务列表
     */
    getQueue(): Task<TResult>[] {
        return Array.from(this.tasks.values())
            .filter(t => t.status === TaskStatus.PENDING || t.status === TaskStatus.RUNNING)
            .sort((a, b) => a.priority - b.priority);
    }

    /**
     * 获取队列统计信息
     */
    getStats(): QueueStats {
        const pending = Array.from(this.tasks.values())
            .filter(t => t.status === TaskStatus.PENDING).length;
        const running = this.queue.pending;

        return {
            pending,
            running,
            completed: this.stats.completed,
            failed: this.stats.failed,
            total: this.stats.total,
            isPaused: this.queue.isPaused,
            concurrency: this.queue.concurrency,
        };
    }

    /**
     * 暂停队列
     */
    pause(): void {
        this.queue.pause();
        console.log('[TaskScheduler] Queue paused');
    }

    /**
     * 恢复队列
     */
    resume(): void {
        this.queue.start();
        console.log('[TaskScheduler] Queue resumed');
    }

    /**
     * 清空队列
     */
    clear(): void {
        this.queue.clear();
        // 标记所有待执行任务为已取消
        for (const task of this.tasks.values()) {
            if (task.status === TaskStatus.PENDING) {
                task.status = TaskStatus.CANCELLED;
                task.completedAt = Date.now();
            }
        }
        console.log('[TaskScheduler] Queue cleared');
    }

    /**
     * 等待队列空闲
     */
    async onIdle(): Promise<void> {
        await this.queue.onIdle();
    }

    /**
     * 设置并发数
     */
    setConcurrency(concurrency: number): void {
        this.queue.concurrency = concurrency;
    }

    /**
     * 获取队列大小
     */
    get size(): number {
        return this.queue.size;
    }

    /**
     * 获取正在执行的任务数
     */
    get pending(): number {
        return this.queue.pending;
    }

    // ============ 事件系统 ============

    /**
     * 添加事件监听器
     */
    on(event: string, listener: (...args: unknown[]) => void): void {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event)!.add(listener);
    }

    /**
     * 移除事件监听器
     */
    off(event: string, listener: (...args: unknown[]) => void): void {
        this.listeners.get(event)?.delete(listener);
    }

    /**
     * 触发事件
     */
    private emit(event: string, ...args: unknown[]): void {
        const eventListeners = this.listeners.get(event);
        if (eventListeners) {
            for (const listener of eventListeners) {
                try {
                    listener(...args);
                } catch (error) {
                    console.error(`[TaskScheduler] Event listener error:`, error);
                }
            }
        }
    }

    /**
     * 清理已完成的任务（释放内存）
     */
    cleanup(maxAge: number = 3600000): number {
        const now = Date.now();
        let cleaned = 0;

        for (const [id, task] of this.tasks) {
            if (
                (task.status === TaskStatus.COMPLETED ||
                    task.status === TaskStatus.FAILED ||
                    task.status === TaskStatus.CANCELLED) &&
                task.completedAt &&
                now - task.completedAt > maxAge
            ) {
                this.tasks.delete(id);
                cleaned++;
            }
        }

        if (cleaned > 0) {
            console.log(`[TaskScheduler] Cleaned ${cleaned} old tasks`);
        }

        return cleaned;
    }
}
