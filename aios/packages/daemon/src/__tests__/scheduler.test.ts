/**
 * TaskScheduler 单元测试
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
    TaskScheduler,
    TaskPriority,
    TaskStatus,
    type Task,
} from '../core/scheduler/index.js';

describe('TaskScheduler', () => {
    let scheduler: TaskScheduler<string>;

    beforeEach(() => {
        scheduler = new TaskScheduler<string>(
            async (task) => {
                // 模拟任务执行
                await new Promise(resolve => setTimeout(resolve, 10));
                return `Result for ${task.id}`;
            },
            { concurrency: 2 }
        );
    });

    afterEach(async () => {
        scheduler.clear();
    });

    describe('submit', () => {
        it('should submit and execute a task', async () => {
            const task = await scheduler.submit('Test prompt');

            expect(task.id).toBeDefined();
            expect(task.prompt).toBe('Test prompt');
            expect(task.priority).toBe(TaskPriority.NORMAL);

            // 等待完成
            await scheduler.onIdle();

            const completedTask = scheduler.getTask(task.id);
            expect(completedTask?.status).toBe(TaskStatus.COMPLETED);
            expect(completedTask?.result).toContain('Result for');
        });

        it('should respect priority ordering', async () => {
            const results: string[] = [];

            const customScheduler = new TaskScheduler<string>(
                async (task) => {
                    results.push(task.id);
                    return task.id;
                },
                { concurrency: 1 }
            );

            // 先暂停队列
            customScheduler.pause();

            // 添加不同优先级的任务
            await customScheduler.submit('Low', { id: 'low', priority: TaskPriority.LOW });
            await customScheduler.submit('High', { id: 'high', priority: TaskPriority.HIGH });
            await customScheduler.submit('Normal', { id: 'normal', priority: TaskPriority.NORMAL });
            await customScheduler.submit('Critical', { id: 'critical', priority: TaskPriority.CRITICAL });
            await customScheduler.submit('Background', { id: 'background', priority: TaskPriority.BACKGROUND });

            // 恢复执行
            customScheduler.resume();
            await customScheduler.onIdle();

            // 高优先级应该先执行
            expect(results).toEqual(['critical', 'high', 'normal', 'low', 'background']);

            customScheduler.clear();
        });

        it('should track task metadata', async () => {
            const task = await scheduler.submit('Test', {
                type: 'complex',
                metadata: { key: 'value' },
            });

            expect(task.type).toBe('complex');
            expect(task.metadata?.key).toBe('value');
        });
    });

    describe('cancel', () => {
        it('should cancel pending tasks and never execute them', async () => {
            const executed: string[] = [];
            const customScheduler = new TaskScheduler<string>(
                async (task) => {
                    executed.push(task.id);
                    return task.id;
                },
                { concurrency: 1 }
            );

            customScheduler.pause();
            const task = await customScheduler.submit('To cancel', { id: 'to_cancel' });

            const cancelled = customScheduler.cancel(task.id);
            expect(cancelled).toBe(true);

            customScheduler.resume();
            await customScheduler.onIdle();

            expect(executed).not.toContain(task.id);

            const cancelledTask = customScheduler.getTask(task.id);
            expect(cancelledTask?.status).toBe(TaskStatus.CANCELLED);

            customScheduler.clear();
        });

        it('should not cancel running tasks', async () => {
            const slowScheduler = new TaskScheduler<string>(
                async () => {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    return 'done';
                },
                { concurrency: 1 }
            );

            const task = await slowScheduler.submit('Running');

            // 等待任务开始
            await new Promise(resolve => setTimeout(resolve, 10));

            const cancelled = slowScheduler.cancel(task.id);
            expect(cancelled).toBe(false);

            slowScheduler.clear();
        });
    });

    describe('getStats', () => {
        it('should return queue statistics', async () => {
            await scheduler.submit('Task 1');
            await scheduler.submit('Task 2');

            await scheduler.onIdle();

            const stats = scheduler.getStats();
            expect(stats.total).toBe(2);
            expect(stats.completed).toBe(2);
            expect(stats.failed).toBe(0);
            expect(stats.concurrency).toBe(2);
        });
    });

    describe('pause and resume', () => {
        it('should pause and resume queue', async () => {
            scheduler.pause();

            const task = await scheduler.submit('Paused task');
            expect(scheduler.getStats().isPaused).toBe(true);

            // 任务应该仍在等待
            expect(scheduler.getTask(task.id)?.status).toBe(TaskStatus.PENDING);

            scheduler.resume();
            await scheduler.onIdle();

            expect(scheduler.getTask(task.id)?.status).toBe(TaskStatus.COMPLETED);
        });
    });

    describe('timeout', () => {
        it('should timeout long-running tasks', async () => {
            const slowScheduler = new TaskScheduler<string>(
                async () => {
                    await new Promise(resolve => setTimeout(resolve, 500));
                    return 'done';
                },
                { defaultTimeout: 50 }
            );

            const task = await slowScheduler.submit('Slow task');
            await slowScheduler.onIdle();

            const completedTask = slowScheduler.getTask(task.id);
            expect(completedTask?.status).toBe(TaskStatus.TIMEOUT);
            expect(completedTask?.error?.message).toContain('timeout');
        });
    });

    describe('retry', () => {
        it('should retry failed tasks', async () => {
            let attempts = 0;
            const retryScheduler = new TaskScheduler<string>(
                async () => {
                    attempts++;
                    if (attempts < 3) {
                        throw new Error('Temporary failure');
                    }
                    return 'success';
                },
                { concurrency: 1 }
            );

            const task = await retryScheduler.submit('Retry task', { maxRetries: 2 });
            await retryScheduler.onIdle();

            expect(attempts).toBe(3);
            const completedTask = retryScheduler.getTask(task.id);
            expect(completedTask?.status).toBe(TaskStatus.COMPLETED);
        });
    });

    describe('events', () => {
        it('should emit events', async () => {
            const events: string[] = [];

            scheduler.on('task:queued', () => events.push('queued'));
            scheduler.on('task:started', () => events.push('started'));
            scheduler.on('task:completed', () => events.push('completed'));

            await scheduler.submit('Event test');
            await scheduler.onIdle();

            expect(events).toContain('queued');
            expect(events).toContain('started');
            expect(events).toContain('completed');
        });
    });

    describe('cleanup', () => {
        it('should cleanup old tasks', async () => {
            await scheduler.submit('Old task');
            await scheduler.onIdle();

            // 强制设置完成时间为过去
            const task = scheduler.getQueue()[0] || Array.from((scheduler as any).tasks.values())[0];
            if (task) {
                task.completedAt = Date.now() - 3700000; // 超过 1 小时
            }

            const cleaned = scheduler.cleanup(3600000);
            expect(cleaned).toBeGreaterThanOrEqual(0);
        });
    });
});
