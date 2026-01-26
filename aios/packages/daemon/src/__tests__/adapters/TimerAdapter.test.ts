/**
 * TimerAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TimerAdapter } from '../../adapters/timer/TimerAdapter';

vi.mock('node-schedule', () => ({
    default: {
        scheduleJob: vi.fn(() => ({ cancel: vi.fn() })),
    },
    scheduleJob: vi.fn(() => ({ cancel: vi.fn() })),
}));

describe('TimerAdapter', () => {
    let adapter: TimerAdapter;

    beforeEach(async () => {
        adapter = new TimerAdapter();
        await adapter.initialize();
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2024-01-01T00:00:00Z'));
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.timer');
            expect(adapter.name).toBe('定时器');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的工具列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('create_timer');
            expect(capabilityIds).toContain('cancel_timer');
            expect(capabilityIds).toContain('list_timers');
        });
    });

    describe('定时器操作', () => {
        it('应该能设置定时器', async () => {
            const result = await adapter.invoke('create_timer', {
                duration: 5,
                name: 'Test timer',
            });

            expect(result.success).toBe(true);
            expect(result.data?.id).toBeDefined();
            expect(result.data?.endTime).toBeDefined();
        });

        it('应该能取消定时器', async () => {
            const setResult = await adapter.invoke('create_timer', {
                duration: 5,
                name: 'Test',
            });

            const cancelResult = await adapter.invoke('cancel_timer', {
                id: (setResult.data as { id: string }).id,
            });

            expect(cancelResult.success).toBe(true);
        });

        it('应该能列出所有定时器', async () => {
            await adapter.invoke('create_timer', { duration: 5, name: 'Timer 1' });
            vi.advanceTimersByTime(1);
            await adapter.invoke('create_timer', { duration: 10, name: 'Timer 2' });

            const result = await adapter.invoke('list_timers', {});

            const timers = result.data?.timers as unknown[];
            expect(Array.isArray(timers)).toBe(true);
            expect(timers.length).toBeGreaterThanOrEqual(2);
        });

        it('应该拒绝无效的持续时间', async () => {
            const negative = await adapter.invoke('create_timer', { duration: -1, name: 'Test' });
            expect(negative.success).toBe(false);

            const zero = await adapter.invoke('create_timer', { duration: 0, name: 'Test' });
            expect(zero.success).toBe(false);
        });
    });
});
