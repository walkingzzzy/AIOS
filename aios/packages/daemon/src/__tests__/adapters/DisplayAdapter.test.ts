/**
 * DisplayAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { DisplayAdapter } from '../../adapters/system/DisplayAdapter';

vi.mock('brightness', () => ({
    default: {
        get: vi.fn(async () => 0.5),
        set: vi.fn(async () => undefined),
    },
}));

describe('DisplayAdapter', () => {
    let adapter: DisplayAdapter;

    beforeEach(async () => {
        adapter = new DisplayAdapter();
        await adapter.initialize();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.display');
            expect(adapter.name).toBe('显示控制');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('get_brightness');
            expect(capabilityIds).toContain('set_brightness');
        });
    });

    describe('亮度控制', () => {
        it('应该能获取当前亮度', async () => {
            const result = await adapter.invoke('get_brightness', {});

            expect(result.success).toBe(true);
            expect((result.data as { brightness?: number }).brightness).toBe(50);
        });

        it('应该能设置亮度并限制范围', async () => {
            const tooHigh = await adapter.invoke('set_brightness', { brightness: 150 });
            expect(tooHigh.success).toBe(true);
            expect((tooHigh.data as { brightness?: number }).brightness).toBe(100);

            const tooLow = await adapter.invoke('set_brightness', { brightness: -10 });
            expect(tooLow.success).toBe(true);
            expect((tooLow.data as { brightness?: number }).brightness).toBe(0);
        });
    });
});
