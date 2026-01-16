/**
 * WindowAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { WindowAdapter } from '../../adapters/apps/WindowAdapter';

describe('WindowAdapter', () => {
    let adapter: WindowAdapter;

    beforeEach(() => {
        adapter = new WindowAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('window');
            expect(adapter.name).toBe('Window Management');
            expect(adapter.permissionLevel).toBe('medium');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('window_list');
            expect(toolNames).toContain('window_focus');
            expect(toolNames).toContain('window_close');
        });
    });

    describe('窗口管理', () => {
        it('应该能列出所有窗口', async () => {
            const result = await adapter.execute('window_list', {});

            expect(result).toBeDefined();
            expect(Array.isArray(result.windows)).toBe(true);
        });

        it('应该能聚焦窗口', async () => {
            const result = await adapter.execute('window_focus', {
                windowId: 'test-window-id'
            });

            expect(result).toBeDefined();
        });

        it('应该能关闭窗口', async () => {
            const result = await adapter.execute('window_close', {
                windowId: 'test-window-id'
            });

            expect(result).toBeDefined();
        });

        it('应该能最小化窗口', async () => {
            const result = await adapter.execute('window_minimize', {
                windowId: 'test-window-id'
            });

            expect(result).toBeDefined();
        });

        it('应该能最大化窗口', async () => {
            const result = await adapter.execute('window_maximize', {
                windowId: 'test-window-id'
            });

            expect(result).toBeDefined();
        });

        it('应该拒绝空窗口ID', async () => {
            await expect(
                adapter.execute('window_focus', { windowId: '' })
            ).rejects.toThrow();
        });
    });
});
