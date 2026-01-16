/**
 * TimerAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TimerAdapter } from '../../adapters/timer/TimerAdapter';

describe('TimerAdapter', () => {
    let adapter: TimerAdapter;

    beforeEach(() => {
        adapter = new TimerAdapter();
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('timer');
            expect(adapter.name).toBe('Timer');
            expect(adapter.permissionLevel).toBe('public');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('timer_set');
            expect(toolNames).toContain('timer_cancel');
            expect(toolNames).toContain('timer_list');
        });
    });

    describe('定时器操作', () => {
        it('应该能设置定时器', async () => {
            const result = await adapter.execute('timer_set', {
                duration: 5000,
                message: 'Test timer'
            });

            expect(result).toBeDefined();
            expect(result.timerId).toBeDefined();
            expect(result.expiresAt).toBeDefined();
        });

        it('应该能取消定时器', async () => {
            const setResult = await adapter.execute('timer_set', {
                duration: 5000,
                message: 'Test'
            });

            const cancelResult = await adapter.execute('timer_cancel', {
                timerId: setResult.timerId
            });

            expect(cancelResult.success).toBe(true);
        });

        it('应该能列出所有定时器', async () => {
            await adapter.execute('timer_set', { duration: 5000, message: 'Timer 1' });
            await adapter.execute('timer_set', { duration: 10000, message: 'Timer 2' });

            const result = await adapter.execute('timer_list', {});

            expect(result.timers).toBeDefined();
            expect(Array.isArray(result.timers)).toBe(true);
            expect(result.timers.length).toBeGreaterThanOrEqual(2);
        });

        it('应该拒绝无效的持续时间', async () => {
            await expect(
                adapter.execute('timer_set', { duration: -1000, message: 'Test' })
            ).rejects.toThrow();

            await expect(
                adapter.execute('timer_set', { duration: 0, message: 'Test' })
            ).rejects.toThrow();
        });
    });
});
