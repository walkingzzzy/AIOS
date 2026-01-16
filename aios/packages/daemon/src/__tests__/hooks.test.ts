/**
 * Hook 系统单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
    BaseHook,
    HookManager,
    HookPriority,
    LoggingHook,
    ProgressHook,
    CallbackHook,
    MetricsHook,
} from '../core/hooks/index.js';
import type {
    TaskStartEvent,
    TaskProgress,
    TaskCompleteEvent,
    TaskErrorEvent,
} from '../core/hooks/index.js';

// 测试用 Hook
class TestHook extends BaseHook {
    public calls: string[] = [];

    constructor(name: string = 'TestHook', priority: HookPriority = HookPriority.NORMAL) {
        super(name, { priority });
    }

    async onTaskStart(event: TaskStartEvent): Promise<void> {
        this.calls.push(`onTaskStart:${event.taskId}`);
    }

    async onProgress(progress: TaskProgress): Promise<void> {
        this.calls.push(`onProgress:${progress.taskId}:${progress.percentage}`);
    }

    async onTaskComplete(event: TaskCompleteEvent): Promise<void> {
        this.calls.push(`onTaskComplete:${event.taskId}`);
    }

    async onTaskError(event: TaskErrorEvent): Promise<void> {
        this.calls.push(`onTaskError:${event.taskId}`);
    }
}

describe('BaseHook', () => {
    it('should create hook with default values', () => {
        const hook = new TestHook('MyHook');
        expect(hook.getName()).toBe('MyHook');
        expect(hook.getPriority()).toBe(HookPriority.NORMAL);
        expect(hook.isEnabled()).toBe(true);
    });

    it('should enable and disable hook', () => {
        const hook = new TestHook();
        expect(hook.isEnabled()).toBe(true);
        hook.disable();
        expect(hook.isEnabled()).toBe(false);
        hook.enable();
        expect(hook.isEnabled()).toBe(true);
    });

    it('should return metadata', () => {
        const hook = new TestHook('MetaHook', HookPriority.HIGH);
        const meta = hook.getMetadata();
        expect(meta.name).toBe('MetaHook');
        expect(meta.priority).toBe(HookPriority.HIGH);
        expect(meta.enabled).toBe(true);
    });
});

describe('HookManager', () => {
    let manager: HookManager;

    beforeEach(() => {
        manager = new HookManager();
    });

    it('should register and unregister hooks', () => {
        const hook = new TestHook();
        manager.register(hook);
        expect(manager.size()).toBe(1);
        expect(manager.getHook('TestHook')).toBe(hook);

        manager.unregister('TestHook');
        expect(manager.size()).toBe(0);
    });

    it('should throw on duplicate registration', () => {
        const hook1 = new TestHook('DuplicateHook');
        const hook2 = new TestHook('DuplicateHook');
        manager.register(hook1);
        expect(() => manager.register(hook2)).toThrow('already registered');
    });

    it('should trigger hooks in priority order', async () => {
        const results: string[] = [];

        class OrderedHook extends BaseHook {
            constructor(name: string, priority: HookPriority) {
                super(name, { priority });
            }
            async onTaskStart(): Promise<void> {
                results.push(this.getName());
            }
        }

        manager.register(new OrderedHook('Low', HookPriority.LOW));
        manager.register(new OrderedHook('High', HookPriority.HIGH));
        manager.register(new OrderedHook('Normal', HookPriority.NORMAL));

        await manager.triggerTaskStart({
            taskId: 'test',
            input: 'test',
            timestamp: Date.now(),
        });

        expect(results).toEqual(['High', 'Normal', 'Low']);
    });

    it('should not trigger disabled hooks', async () => {
        const hook = new TestHook();
        hook.disable();
        manager.register(hook);

        await manager.triggerTaskStart({
            taskId: 'test',
            input: 'test',
            timestamp: Date.now(),
        });

        expect(hook.calls.length).toBe(0);
    });

    it('should isolate hook errors', async () => {
        class ErrorHook extends BaseHook {
            constructor() {
                super('ErrorHook');
            }
            async onTaskStart(): Promise<void> {
                throw new Error('Hook error');
            }
        }

        const goodHook = new TestHook('GoodHook');
        manager.register(new ErrorHook());
        manager.register(goodHook);

        // Should not throw
        await manager.triggerTaskStart({
            taskId: 'test',
            input: 'test',
            timestamp: Date.now(),
        });

        expect(goodHook.calls.length).toBe(1);
    });
});

describe('LoggingHook', () => {
    it('should create with default log level', () => {
        const hook = new LoggingHook();
        expect(hook.getName()).toBe('LoggingHook');
        expect(hook.getPriority()).toBe(HookPriority.HIGHEST);
    });
});

describe('ProgressHook', () => {
    it('should track task progress', async () => {
        const hook = new ProgressHook();
        const taskId = 'test-task';

        await hook.onTaskStart({
            taskId,
            input: 'test',
            timestamp: Date.now(),
        });

        let state = hook.getProgress(taskId);
        expect(state?.status).toBe('running');
        expect(state?.percentage).toBe(0);

        await hook.onProgress({
            taskId,
            currentStep: 1,
            totalSteps: 2,
            percentage: 50,
        });

        state = hook.getProgress(taskId);
        expect(state?.percentage).toBe(50);
    });

    it('should notify listeners', async () => {
        const hook = new ProgressHook();
        const notifications: string[] = [];

        hook.addListener((taskId, state) => {
            notifications.push(`${taskId}:${state.status}`);
        });

        await hook.onTaskStart({
            taskId: 'task1',
            input: 'test',
            timestamp: Date.now(),
        });

        expect(notifications).toContain('task1:running');
    });
});

describe('CallbackHook', () => {
    it('should emit events to handler', async () => {
        const events: any[] = [];
        const hook = new CallbackHook((event) => {
            events.push(event);
        });

        await hook.onTaskStart({
            taskId: 'task1',
            input: 'test input',
            timestamp: Date.now(),
        });

        expect(events.length).toBe(1);
        expect(events[0].type).toBe('task:start');
        expect(events[0].taskId).toBe('task1');
    });

    it('should filter events', async () => {
        const events: any[] = [];
        const hook = new CallbackHook((event) => {
            events.push(event);
        }, { events: ['task:complete'] });

        await hook.onTaskStart({
            taskId: 'task1',
            input: 'test',
            timestamp: Date.now(),
        });

        expect(events.length).toBe(0);
    });
});

describe('MetricsHook', () => {
    it('should track task metrics', async () => {
        const hook = new MetricsHook();

        await hook.onTaskStart({
            taskId: 'task1',
            input: 'test',
            timestamp: Date.now(),
        });

        await hook.onTaskComplete({
            taskId: 'task1',
            result: { success: true, response: 'done', tier: 'fast', executionTime: 100 },
            timestamp: Date.now(),
            duration: 100,
        });

        const metrics = hook.getMetrics();
        expect(metrics.tasks.totalTasks).toBe(1);
        expect(metrics.tasks.completedTasks).toBe(1);
        expect(hook.getTaskSuccessRate()).toBe(1);
    });

    it('should track tool metrics', async () => {
        const hook = new MetricsHook();

        await hook.onToolResult({
            toolId: 'tool1',
            adapterId: 'adapter1',
            capabilityId: 'cap1',
            params: {},
            timestamp: Date.now(),
            success: true,
            duration: 50,
        });

        await hook.onToolResult({
            toolId: 'tool2',
            adapterId: 'adapter1',
            capabilityId: 'cap1',
            params: {},
            timestamp: Date.now(),
            success: false,
            duration: 100,
        });

        expect(hook.getToolSuccessRate()).toBe(0.5);
    });
});
