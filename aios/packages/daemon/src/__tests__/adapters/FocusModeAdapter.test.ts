/**
 * FocusModeAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const runPlatformCommandMock = vi.hoisted(() => vi.fn(async () => ({
    stdout: '1',
    stderr: '',
    exitCode: 0,
})));

vi.mock('@aios/shared', async () => {
    const actual = await vi.importActual<typeof import('@aios/shared')>('@aios/shared');
    return {
        ...actual,
        runPlatformCommand: runPlatformCommandMock,
        getPlatform: () => 'darwin',
    };
});

import { FocusModeAdapter } from '../../adapters/system/FocusModeAdapter';

describe('FocusModeAdapter', () => {
    let adapter: FocusModeAdapter;

    beforeEach(() => {
        adapter = new FocusModeAdapter();
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2024-01-01T00:00:00Z'));
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.focusmode');
            expect(adapter.name).toBe('专注模式');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('dnd_status');
            expect(capabilityIds).toContain('dnd_toggle');
            expect(capabilityIds).toContain('focus_start');
            expect(capabilityIds).toContain('focus_stop');
        });
    });

    describe('专注模式', () => {
        it('应该能获取勿扰状态', async () => {
            const result = await adapter.invoke('dnd_status', {});

            expect(result.success).toBe(true);
            expect((result.data as { enabled?: boolean }).enabled).toBe(true);
        });

        it('应该能开始和结束专注', async () => {
            const startResult = await adapter.invoke('focus_start', { duration: 1 });
            expect(startResult.success).toBe(true);

            vi.runOnlyPendingTimers();

            const stopResult = await adapter.invoke('focus_stop', {});
            expect(stopResult.success).toBe(true);
        });
    });
});
