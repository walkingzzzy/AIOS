/**
 * WorkerPool - Worker 池管理
 */

import type { Worker, WorkerStatus, SubTask } from './types.js';

/**
 * Worker 池配置
 */
export interface WorkerPoolConfig {
    /** 最大 Worker 数量 */
    maxWorkers: number;
    /** Worker 超时时间 (ms) */
    timeout: number;
}

/**
 * Worker 执行器
 */
export type WorkerExecutor = (task: SubTask) => Promise<unknown>;

/**
 * Worker 池
 */
export class WorkerPool {
    private workers: Map<string, Worker> = new Map();
    private executor: WorkerExecutor;
    private config: WorkerPoolConfig;

    constructor(executor: WorkerExecutor, config: Partial<WorkerPoolConfig> = {}) {
        this.executor = executor;
        this.config = {
            maxWorkers: config.maxWorkers ?? 5,
            timeout: config.timeout ?? 60000,
        };

        // 初始化默认 Worker
        this.initializeWorkers();
    }

    /**
     * 初始化 Worker
     */
    private initializeWorkers(): void {
        for (let i = 1; i <= this.config.maxWorkers; i++) {
            const worker: Worker = {
                id: `worker_${i}`,
                name: `Worker ${i}`,
                capabilities: ['general'],
                status: 'idle',
                completedTasks: 0,
                avgExecutionTime: 0,
            };
            this.workers.set(worker.id, worker);
        }
        console.log(`[WorkerPool] Initialized ${this.config.maxWorkers} workers`);
    }

    /**
     * 获取可用 Worker
     */
    getAvailable(): Worker | undefined {
        for (const worker of this.workers.values()) {
            if (worker.status === 'idle') {
                return worker;
            }
        }
        return undefined;
    }

    /**
     * 分配任务给 Worker
     */
    async assign(task: SubTask): Promise<{ workerId: string; result: unknown }> {
        const worker = this.getAvailable();
        if (!worker) {
            throw new Error('No available workers');
        }

        worker.status = 'busy';
        worker.currentTaskId = task.id;
        task.workerId = worker.id;
        task.status = 'running';

        const startTime = Date.now();

        try {
            // 执行任务（带超时）
            const result = await this.executeWithTimeout(task, this.config.timeout);

            // 更新 Worker 统计
            const duration = Date.now() - startTime;
            worker.completedTasks++;
            worker.avgExecutionTime =
                (worker.avgExecutionTime * (worker.completedTasks - 1) + duration) / worker.completedTasks;

            task.status = 'completed';
            task.result = result;
            task.actualTime = duration;

            return { workerId: worker.id, result };
        } catch (error) {
            task.status = 'failed';
            task.error = error instanceof Error ? error.message : String(error);
            throw error;
        } finally {
            worker.status = 'idle';
            worker.currentTaskId = undefined;
        }
    }

    /**
     * 带超时的执行
     */
    private async executeWithTimeout(task: SubTask, timeout: number): Promise<unknown> {
        return Promise.race([
            this.executor(task),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error(`Worker timeout after ${timeout}ms`)), timeout)
            ),
        ]);
    }

    /**
     * 并行执行多个任务
     */
    async executeParallel(tasks: SubTask[]): Promise<Map<string, unknown>> {
        const results = new Map<string, unknown>();
        const pending = [...tasks];
        const running: Promise<void>[] = [];

        while (pending.length > 0 || running.length > 0) {
            // 尝试分配更多任务
            while (pending.length > 0 && this.getAvailable()) {
                const task = pending.shift()!;
                const promise = this.assign(task)
                    .then(({ result }) => {
                        results.set(task.id, result);
                    })
                    .catch(error => {
                        results.set(task.id, { error: error.message });
                    });
                running.push(promise);
            }

            // 等待至少一个任务完成
            if (running.length > 0) {
                await Promise.race(running);
                // 移除已完成的 promise
                const completedIndices: number[] = [];
                for (let i = 0; i < running.length; i++) {
                    // 检查是否已完成
                    const completed = await Promise.race([
                        running[i].then(() => true),
                        Promise.resolve(false),
                    ]);
                    if (completed) {
                        completedIndices.push(i);
                    }
                }
                // 从后向前移除
                for (const idx of completedIndices.reverse()) {
                    running.splice(idx, 1);
                }
            }
        }

        return results;
    }

    /**
     * 获取 Worker 状态
     */
    getStats(): { total: number; idle: number; busy: number } {
        let idle = 0, busy = 0;
        for (const worker of this.workers.values()) {
            if (worker.status === 'idle') idle++;
            else if (worker.status === 'busy') busy++;
        }
        return { total: this.workers.size, idle, busy };
    }

    /**
     * 获取所有 Worker
     */
    getWorkers(): Worker[] {
        return Array.from(this.workers.values());
    }
}
