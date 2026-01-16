/**
 * FocusModeAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { FocusModeAdapter } from '../../adapters/system/FocusModeAdapter';

describe('FocusModeAdapter', () => {
    let adapter: FocusModeAdapter;

    beforeEach(() => {
        adapter = new FocusModeAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('focus_mode');
            expect(adapter.name).toBe('Focus Mode');
            expect(adapter.permissionLevel).toBe('medium');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('focus_enable');
            expect(toolNames).toContain('focus_disable');
            expect(toolNames).toContain('focus_get_status');
        });
    });

    describe('专注模式控制', () => {
        it('应该能启用专注模式', async () => {
            const result = await adapter.execute('focus_enable', {
                duration: 3600
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
            expect(result.enabled).toBe(true);
        });

        it('应该能禁用专注模式', async () => {
            await adapter.execute('focus_enable', { duration: 3600 });

            const result = await adapter.execute('focus_disable', {});

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
            expect(result.enabled).toBe(false);
        });

        it('应该能获取专注模式状态', async () => {
            const result = await adapter.execute('focus_get_status', {});

            expect(result).toBeDefined();
            expect(typeof result.enabled).toBe('boolean');
        });

        it('应该能设置专注模式配置', async () => {
            const result = await adapter.execute('focus_configure', {
                blockNotifications: true,
                blockApps: ['Safari', 'Chrome'],
                allowedApps: ['VSCode']
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该拒绝无效的持续时间', async () => {
            await expect(
                adapter.execute('focus_enable', { duration: -1 })
            ).rejects.toThrow();

            await expect(
                adapter.execute('focus_enable', { duration: 0 })
            ).rejects.toThrow();
        });
    });
});
