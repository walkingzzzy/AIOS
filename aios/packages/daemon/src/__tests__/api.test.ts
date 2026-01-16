/**
 * 进度 API 单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import Database from 'better-sqlite3';
import { TaskAPI } from '../api/TaskAPI.js';
import { ProgressAPI } from '../api/ProgressAPI.js';
import { TaskScheduler } from '../core/scheduler/index.js';
import { SessionManager } from '../core/storage/index.js';
import { JSONRPCHandler } from '../core/JSONRPCHandler.js';

describe('TaskAPI', () => {
    let db: Database.Database;
    let scheduler: TaskScheduler<unknown>;
    let sessionManager: SessionManager;
    let taskAPI: TaskAPI;
    let handler: JSONRPCHandler;

    beforeEach(() => {
        db = new Database(':memory:');
        scheduler = new TaskScheduler(async (task) => {
            return `Result for ${task.id}`;
        }, { concurrency: 2 });
        sessionManager = new SessionManager(db);
        taskAPI = new TaskAPI(scheduler, sessionManager);
        handler = new JSONRPCHandler();
        taskAPI.registerMethods(handler);
    });

    describe('submit', () => {
        it('should submit a task', async () => {
            const result = await taskAPI.submit({ prompt: 'Hello world' });
            expect(result.taskId).toBeDefined();
            // 任务可能已经开始执行，所以接受 pending 或 running
            expect(['pending', 'running']).toContain(result.status);
        });

        it('should throw on empty prompt', async () => {
            await expect(taskAPI.submit({ prompt: '' })).rejects.toThrow('prompt');
        });

        it('should accept priority parameter', async () => {
            const result = await taskAPI.submit({
                prompt: 'High priority task',
                priority: 'high'
            });
            expect(result.taskId).toBeDefined();
        });
    });

    describe('cancel', () => {
        it('should cancel a pending task', async () => {
            scheduler.pause();
            const submitResult = await taskAPI.submit({ prompt: 'To cancel' });
            const cancelResult = await taskAPI.cancel({ taskId: submitResult.taskId });
            expect(cancelResult.success).toBe(true);
        });

        it('should fail to cancel running task', async () => {
            const slowScheduler = new TaskScheduler<unknown>(async () => {
                await new Promise(r => setTimeout(r, 100));
                return 'done';
            }, { concurrency: 1 });
            const api = new TaskAPI(slowScheduler, sessionManager);

            const submitResult = await api.submit({ prompt: 'Running' });
            await new Promise(r => setTimeout(r, 10));

            const cancelResult = await api.cancel({ taskId: submitResult.taskId });
            expect(cancelResult.success).toBe(false);

            slowScheduler.clear();
        });
    });

    describe('getStatus', () => {
        it('should get task status', async () => {
            const submitResult = await taskAPI.submit({ prompt: 'Test task' });
            const status = await taskAPI.getStatus({ taskId: submitResult.taskId });

            expect(status).not.toBeNull();
            expect(status?.taskId).toBe(submitResult.taskId);
            expect(status?.prompt).toBe('Test task');
        });

        it('should return null for unknown task', async () => {
            const status = await taskAPI.getStatus({ taskId: 'unknown_task' });
            expect(status).toBeNull();
        });
    });

    describe('getQueue', () => {
        it('should get queue status', async () => {
            scheduler.pause();
            await taskAPI.submit({ prompt: 'Task 1' });
            await taskAPI.submit({ prompt: 'Task 2' });

            const queue = await taskAPI.getQueue();
            expect(queue.pending).toBeGreaterThanOrEqual(2);
            expect(queue.tasks.length).toBeGreaterThanOrEqual(2);
        });
    });

    describe('getHistory', () => {
        it('should get task history', async () => {
            await taskAPI.submit({ prompt: 'Task 1' });
            await taskAPI.submit({ prompt: 'Task 2' });

            const history = await taskAPI.getHistory();
            expect(history.total).toBeGreaterThanOrEqual(2);
            expect(history.data.length).toBeGreaterThanOrEqual(2);
        });
    });

    describe('JSON-RPC integration', () => {
        it('should register methods', async () => {
            const response = await handler.handleRequest({
                jsonrpc: '2.0',
                id: 1,
                method: 'task.submit',
                params: { prompt: 'Test via RPC' },
            });

            expect(response.error).toBeUndefined();
            expect(response.result).toBeDefined();
            expect((response.result as any).taskId).toBeDefined();
        });
    });
});

describe('ProgressAPI', () => {
    let progressAPI: ProgressAPI;

    beforeEach(() => {
        progressAPI = new ProgressAPI();
    });

    describe('subscribe', () => {
        it('should add subscriber', () => {
            const unsubscribe = progressAPI.subscribe(() => { });
            expect(progressAPI.subscriberCount).toBe(1);
            unsubscribe();
            expect(progressAPI.subscriberCount).toBe(0);
        });
    });

    describe('emit', () => {
        it('should broadcast events to subscribers', () => {
            const events: any[] = [];
            progressAPI.subscribe((event) => events.push(event));

            progressAPI.emit('test:event', 'task123', { key: 'value' });

            expect(events.length).toBe(1);
            expect(events[0].type).toBe('test:event');
            expect(events[0].taskId).toBe('task123');
        });
    });

    describe('emitProgress', () => {
        it('should emit progress with percentage', () => {
            const events: any[] = [];
            progressAPI.subscribe((event) => events.push(event));

            progressAPI.emitProgress('task123', 5, 10, 'Half done');

            expect(events.length).toBe(1);
            expect(events[0].data.currentStep).toBe(5);
            expect(events[0].data.totalSteps).toBe(10);
            expect(events[0].data.percentage).toBe(50);
        });
    });

    describe('getHook', () => {
        it('should return a CallbackHook', () => {
            const hook = progressAPI.getHook();
            expect(hook.getName()).toBe('CallbackHook');
        });
    });
});
