/**
 * PowerAdapter 单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { PowerAdapter } from '../../adapters/system/PowerAdapter.js';

// Mock runPlatformCommand
vi.mock('@aios/shared', async () => {
    const actual = await vi.importActual('@aios/shared');
    return {
        ...actual,
        runPlatformCommand: vi.fn().mockResolvedValue(''),
    };
});

describe('PowerAdapter', () => {
    let adapter: PowerAdapter;

    beforeEach(() => {
        adapter = new PowerAdapter();
    });

    describe('基本属性', () => {
        it('应该有正确的 id', () => {
            expect(adapter.id).toBe('com.aios.adapter.power');
        });

        it('应该有正确的名称', () => {
            expect(adapter.name).toBe('电源管理');
        });

        it('应该有 6 个能力', () => {
            expect(adapter.capabilities).toHaveLength(6);
        });
    });

    describe('checkAvailability', () => {
        it('应该返回 true', async () => {
            const available = await adapter.checkAvailability();
            expect(available).toBe(true);
        });
    });

    describe('lock_screen', () => {
        it('应该成功锁屏', async () => {
            const result = await adapter.invoke('lock_screen', {});
            expect(result.success).toBe(true);
            expect(result.data?.action).toBe('lock_screen');
        });
    });

    describe('sleep', () => {
        it('应该成功休眠', async () => {
            const result = await adapter.invoke('sleep', {});
            expect(result.success).toBe(true);
            expect(result.data?.action).toBe('sleep');
        });
    });

    describe('shutdown', () => {
        it('应该要求确认', async () => {
            const result = await adapter.invoke('shutdown', {});
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('CONFIRMATION_REQUIRED');
        });

        it('确认后应该成功', async () => {
            const result = await adapter.invoke('shutdown', { confirm: true });
            expect(result.success).toBe(true);
            expect(result.data?.action).toBe('shutdown');
            expect(result.data?.delay).toBeGreaterThanOrEqual(30);
        });

        it('应该强制最小延迟 30 秒', async () => {
            const result = await adapter.invoke('shutdown', { confirm: true, delay: 5 });
            expect(result.success).toBe(true);
            expect(result.data?.delay).toBe(30);
        });
    });

    describe('restart', () => {
        it('应该要求确认', async () => {
            const result = await adapter.invoke('restart', {});
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('CONFIRMATION_REQUIRED');
        });

        it('确认后应该成功', async () => {
            const result = await adapter.invoke('restart', { confirm: true });
            expect(result.success).toBe(true);
            expect(result.data?.action).toBe('restart');
        });
    });

    describe('logout', () => {
        it('应该要求确认', async () => {
            const result = await adapter.invoke('logout', {});
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('CONFIRMATION_REQUIRED');
        });

        it('确认后应该成功', async () => {
            const result = await adapter.invoke('logout', { confirm: true });
            expect(result.success).toBe(true);
            expect(result.data?.action).toBe('logout');
        });
    });

    describe('cancel_shutdown', () => {
        it('应该成功取消关机', async () => {
            const result = await adapter.invoke('cancel_shutdown', {});
            expect(result.success).toBe(true);
            expect(result.data?.action).toBe('cancel_shutdown');
        });
    });

    describe('错误处理', () => {
        it('应该处理未知能力', async () => {
            const result = await adapter.invoke('unknown_capability', {});
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('CAPABILITY_NOT_FOUND');
        });
    });
});
