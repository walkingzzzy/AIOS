/**
 * WindowAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { WindowAdapter } from '../../adapters/apps/WindowAdapter';

vi.mock('@aios/shared', async () => {
    const actual = await vi.importActual<typeof import('@aios/shared')>('@aios/shared');
    return {
        ...actual,
        runPlatformCommand: vi.fn(async () => ({ stdout: '', stderr: '', exitCode: 0 })),
    };
});

describe('WindowAdapter', () => {
    let adapter: WindowAdapter;

    beforeEach(() => {
        adapter = new WindowAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.window');
            expect(adapter.name).toBe('窗口管理');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的工具列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('maximize');
            expect(capabilityIds).toContain('minimize');
            expect(capabilityIds).toContain('close_window');
        });
    });

    describe('窗口管理', () => {
        it('应该能最大化窗口', async () => {
            const result = await adapter.invoke('maximize', {});
            expect(result.success).toBe(true);
        });

        it('应该能最小化窗口', async () => {
            const result = await adapter.invoke('minimize', {});
            expect(result.success).toBe(true);
        });

        it('应该能关闭窗口', async () => {
            const result = await adapter.invoke('close_window', {});
            expect(result.success).toBe(true);
        });

        it('应该能切换应用', async () => {
            const result = await adapter.invoke('switch_app', {});
            expect(result.success).toBe(true);
        });

        it('未知能力应返回失败', async () => {
            const result = await adapter.invoke('unknown_capability', {});
            expect(result.success).toBe(false);
        });
    });
});
