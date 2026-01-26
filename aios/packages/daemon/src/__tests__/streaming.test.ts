/**
 * 流式响应和 LLM 钩子测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
    HookManager,
    LLMMetricsHook,
    LLMLoggingHook,
    LLMCostTrackingHook,
    type LLMRequestEvent,
    type LLMResponseEvent,
    type LLMStreamChunkEvent,
} from '../core/hooks/index.js';
import { EventStream, EventType, getEventStream } from '../core/events/index.js';

describe('LLM Hooks', () => {
    let hookManager: HookManager;

    beforeEach(() => {
        hookManager = new HookManager();
    });

    describe('LLMMetricsHook', () => {
        it('should track LLM request metrics', async () => {
            const metricsHook = new LLMMetricsHook();
            hookManager.register(metricsHook);

            const requestEvent: LLMRequestEvent = {
                requestId: 'req_123',
                taskId: 'task_456',
                engineId: 'openai',
                model: 'gpt-4',
                messages: [{ role: 'user', content: 'Hello' }],
                timestamp: Date.now(),
            };

            await hookManager.triggerLLMRequest(requestEvent);

            const metrics = metricsHook.getAggregateMetrics();
            expect(metrics.totalRequests).toBe(1);
        });

        it('should track LLM response metrics with usage', async () => {
            const metricsHook = new LLMMetricsHook();
            hookManager.register(metricsHook);

            const requestEvent: LLMRequestEvent = {
                requestId: 'req_123',
                engineId: 'openai',
                model: 'gpt-4',
                messages: [{ role: 'user', content: 'Hello' }],
                timestamp: Date.now() - 1000,
            };

            const responseEvent: LLMResponseEvent = {
                requestId: 'req_123',
                engineId: 'openai',
                model: 'gpt-4',
                content: 'Hello there!',
                finishReason: 'stop',
                usage: {
                    promptTokens: 10,
                    completionTokens: 5,
                    totalTokens: 15,
                },
                timestamp: Date.now(),
                latency: 1000,
            };

            await hookManager.triggerLLMRequest(requestEvent);
            await hookManager.triggerLLMResponse(responseEvent);

            const metrics = metricsHook.getAggregateMetrics();
            expect(metrics.successfulRequests).toBe(1);
            expect(metrics.totalTokens).toBe(15);
            expect(metrics.averageLatency).toBe(1000);
        });

        it('should track stream chunks', async () => {
            const metricsHook = new LLMMetricsHook();
            hookManager.register(metricsHook);

            const requestEvent: LLMRequestEvent = {
                requestId: 'req_stream',
                engineId: 'openai',
                model: 'gpt-4',
                messages: [{ role: 'user', content: 'Hello' }],
                options: { stream: true },
                timestamp: Date.now() - 500,
            };

            await hookManager.triggerLLMRequest(requestEvent);

            // 发送多个流式块
            for (let i = 0; i < 5; i++) {
                const chunkEvent: LLMStreamChunkEvent = {
                    requestId: 'req_stream',
                    engineId: 'openai',
                    content: 'chunk',
                    finished: i === 4,
                    finishReason: i === 4 ? 'stop' : null,
                    chunkIndex: i,
                    timestamp: Date.now(),
                };
                await hookManager.triggerLLMStreamChunk(chunkEvent);
            }

            const metrics = metricsHook.getAggregateMetrics();
            expect(metrics.streamRequests).toBe(1);
            expect(metrics.averageChunksPerStream).toBe(5);
        });

        it('should get metrics by model', async () => {
            const metricsHook = new LLMMetricsHook();
            hookManager.register(metricsHook);

            // 模拟多个模型的请求
            const models = ['gpt-4', 'gpt-3.5-turbo', 'gpt-4'];
            for (const model of models) {
                await hookManager.triggerLLMRequest({
                    requestId: `req_${Math.random()}`,
                    engineId: 'openai',
                    model,
                    messages: [],
                    timestamp: Date.now(),
                });
                await hookManager.triggerLLMResponse({
                    requestId: `req_${Math.random()}`,
                    engineId: 'openai',
                    model,
                    content: 'response',
                    usage: { promptTokens: 10, completionTokens: 5, totalTokens: 15 },
                    timestamp: Date.now(),
                    latency: 100,
                });
            }

            const byModel = metricsHook.getMetricsByModel();
            expect(byModel.get('gpt-4')?.requests).toBe(2);
            expect(byModel.get('gpt-3.5-turbo')?.requests).toBe(1);
        });
    });

    describe('LLMLoggingHook', () => {
        it('should log LLM requests and responses', async () => {
            const loggingHook = new LLMLoggingHook({
                logMessageContent: true,
                logResponseContent: true,
            });
            hookManager.register(loggingHook);

            await hookManager.triggerLLMRequest({
                requestId: 'req_log',
                engineId: 'openai',
                model: 'gpt-4',
                messages: [{ role: 'user', content: 'Test message' }],
                timestamp: Date.now(),
            });

            await hookManager.triggerLLMResponse({
                requestId: 'req_log',
                engineId: 'openai',
                model: 'gpt-4',
                content: 'Test response',
                timestamp: Date.now(),
                latency: 100,
            });

            const logs = loggingHook.getLogs();
            expect(logs.length).toBe(2);
            expect(logs[0].type).toBe('request');
            expect(logs[1].type).toBe('response');
        });

        it('should filter logs by request ID', async () => {
            const loggingHook = new LLMLoggingHook();
            hookManager.register(loggingHook);

            for (let i = 0; i < 3; i++) {
                await hookManager.triggerLLMRequest({
                    requestId: `req_${i}`,
                    engineId: 'openai',
                    model: 'gpt-4',
                    messages: [],
                    timestamp: Date.now(),
                });
            }

            const logsForReq1 = loggingHook.getLogsByRequest('req_1');
            expect(logsForReq1.length).toBe(1);
            expect(logsForReq1[0].requestId).toBe('req_1');
        });

        it('should truncate long content', async () => {
            const loggingHook = new LLMLoggingHook({
                maxContentLength: 50,
            });
            hookManager.register(loggingHook);

            const longContent = 'a'.repeat(100);
            await hookManager.triggerLLMResponse({
                requestId: 'req_long',
                engineId: 'openai',
                model: 'gpt-4',
                content: longContent,
                timestamp: Date.now(),
                latency: 100,
            });

            const logs = loggingHook.getLogs();
            const responseLog = logs[0];
            const loggedContent = (responseLog.data?.content as string) || '';
            expect(loggedContent.length).toBeLessThan(100);
            expect(loggedContent).toContain('truncated');
        });
    });

    describe('LLMCostTrackingHook', () => {
        it('should track LLM costs', async () => {
            const costHook = new LLMCostTrackingHook();
            hookManager.register(costHook);

            await hookManager.triggerLLMResponse({
                requestId: 'req_cost',
                engineId: 'openai',
                model: 'gpt-4',
                content: 'response',
                usage: {
                    promptTokens: 1000,
                    completionTokens: 500,
                    totalTokens: 1500,
                },
                timestamp: Date.now(),
                latency: 100,
            });

            const summary = costHook.getSummary();
            expect(summary.totalRequests).toBe(1);
            expect(summary.totalTokens).toBe(1500);
            expect(summary.totalCost).toBeGreaterThan(0);
        });

        it('should calculate costs for different models', async () => {
            const costHook = new LLMCostTrackingHook();
            hookManager.register(costHook);

            // GPT-4 请求
            await hookManager.triggerLLMResponse({
                requestId: 'req_gpt4',
                engineId: 'openai',
                model: 'gpt-4',
                content: 'response',
                usage: { promptTokens: 1000, completionTokens: 500, totalTokens: 1500 },
                timestamp: Date.now(),
                latency: 100,
            });

            // GPT-3.5 请求（应该更便宜）
            await hookManager.triggerLLMResponse({
                requestId: 'req_gpt35',
                engineId: 'openai',
                model: 'gpt-3.5-turbo',
                content: 'response',
                usage: { promptTokens: 1000, completionTokens: 500, totalTokens: 1500 },
                timestamp: Date.now(),
                latency: 100,
            });

            const summary = costHook.getSummary();
            const gpt4Cost = summary.costByModel.get('gpt-4')?.cost ?? 0;
            const gpt35Cost = summary.costByModel.get('gpt-3.5-turbo')?.cost ?? 0;

            expect(gpt4Cost).toBeGreaterThan(gpt35Cost);
        });

        it('should track daily costs', async () => {
            const costHook = new LLMCostTrackingHook();
            hookManager.register(costHook);

            await hookManager.triggerLLMResponse({
                requestId: 'req_today',
                engineId: 'openai',
                model: 'gpt-4',
                content: 'response',
                usage: { promptTokens: 100, completionTokens: 50, totalTokens: 150 },
                timestamp: Date.now(),
                latency: 100,
            });

            const todayCost = costHook.getTodayCost();
            expect(todayCost).toBeGreaterThan(0);
        });

        it('should format costs correctly', () => {
            const costHook = new LLMCostTrackingHook();

            expect(costHook.formatCost(0.005)).toContain('$');
            expect(costHook.formatCost(1.5)).toBe('$1.5000');
        });
    });
});

describe('EventStream', () => {
    let eventStream: EventStream;

    beforeEach(() => {
        eventStream = new EventStream({ maxEvents: 100 });
    });

    afterEach(() => {
        eventStream.destroy();
    });

    it('should emit and store events', () => {
        eventStream.emit(EventType.TASK_START, 'TestSource', { input: 'test' }, { taskId: 'task_1' });

        const events = eventStream.getRecent(10);
        expect(events.length).toBe(1);
        expect(events[0].type).toBe(EventType.TASK_START);
        expect(events[0].source).toBe('TestSource');
        expect(events[0].taskId).toBe('task_1');
    });

    it('should subscribe to events', () => {
        const callback = vi.fn();
        const subscription = eventStream.subscribe(callback);

        eventStream.emit(EventType.TASK_PROGRESS, 'Test', { progress: 50 });

        expect(callback).toHaveBeenCalledTimes(1);
        expect(callback).toHaveBeenCalledWith(expect.objectContaining({
            type: EventType.TASK_PROGRESS,
        }));

        subscription.unsubscribe();
    });

    it('should filter events by type', () => {
        const callback = vi.fn();
        eventStream.subscribe(callback, {
            filter: { types: [EventType.TASK_COMPLETE] },
        });

        eventStream.emit(EventType.TASK_START, 'Test', {});
        eventStream.emit(EventType.TASK_COMPLETE, 'Test', {});
        eventStream.emit(EventType.TASK_ERROR, 'Test', {});

        expect(callback).toHaveBeenCalledTimes(1);
    });

    it('should query events by task ID', () => {
        eventStream.emit(EventType.TASK_START, 'Test', {}, { taskId: 'task_A' });
        eventStream.emit(EventType.TASK_PROGRESS, 'Test', {}, { taskId: 'task_A' });
        eventStream.emit(EventType.TASK_START, 'Test', {}, { taskId: 'task_B' });

        const taskAEvents = eventStream.queryByTask('task_A');
        expect(taskAEvents.length).toBe(2);
    });

    it('should prune old events', () => {
        const smallStream = new EventStream({ maxEvents: 5 });

        for (let i = 0; i < 10; i++) {
            smallStream.emit(EventType.SYSTEM_INFO, 'Test', { index: i });
        }

        const events = smallStream.getRecent(100);
        expect(events.length).toBe(5);

        smallStream.destroy();
    });

    it('should get event statistics', () => {
        eventStream.emit(EventType.TASK_START, 'Test', {});
        eventStream.emit(EventType.TASK_START, 'Test', {});
        eventStream.emit(EventType.TASK_COMPLETE, 'Test', {});

        const stats = eventStream.getStats();
        expect(stats.totalEvents).toBe(3);
        expect(stats.eventsByType[EventType.TASK_START]).toBe(2);
        expect(stats.eventsByType[EventType.TASK_COMPLETE]).toBe(1);
    });

    it('should include history when subscribing', () => {
        eventStream.emit(EventType.TASK_START, 'Test', { step: 1 });
        eventStream.emit(EventType.TASK_START, 'Test', { step: 2 });

        const callback = vi.fn();
        eventStream.subscribe(callback, {
            includeHistory: true,
            historyLimit: 10,
        });

        // 历史事件应该被回调
        expect(callback).toHaveBeenCalledTimes(2);
    });
});

describe('Streaming Performance', () => {
    it('should handle high-frequency stream chunks', async () => {
        const hookManager = new HookManager();
        const metricsHook = new LLMMetricsHook();
        hookManager.register(metricsHook);

        const startTime = Date.now();
        const chunkCount = 100;

        // 发送请求
        await hookManager.triggerLLMRequest({
            requestId: 'perf_test',
            engineId: 'test',
            model: 'test-model',
            messages: [],
            options: { stream: true },
            timestamp: startTime,
        });

        // 发送大量流式块
        for (let i = 0; i < chunkCount; i++) {
            await hookManager.triggerLLMStreamChunk({
                requestId: 'perf_test',
                engineId: 'test',
                content: `chunk_${i}`,
                finished: i === chunkCount - 1,
                chunkIndex: i,
                timestamp: Date.now(),
            });
        }

        const endTime = Date.now();
        const duration = endTime - startTime;

        // 应该在合理时间内完成
        expect(duration).toBeLessThan(1000);

        const metrics = metricsHook.getAggregateMetrics();
        expect(metrics.streamRequests).toBe(1);
        expect(metrics.averageChunksPerStream).toBe(chunkCount);
    });
});
