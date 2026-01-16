/**
 * AppsAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { AppsAdapter } from '../../adapters/apps/AppsAdapter';

describe('AppsAdapter', () => {
    let adapter: AppsAdapter;

    beforeEach(() => {
        adapter = new AppsAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('apps');
            expect(adapter.name).toBe('Application Management');
            expect(adapter.permissionLevel).toBe('medium');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('apps_launch');
            expect(toolNames).toContain('apps_close');
            expect(toolNames).toContain('apps_list_running');
        });
    });

    describe('应用管理', () => {
        it('应该能列出运行中的应用', async () => {
            const result = await adapter.execute('apps_list_running', {});

            expect(result).toBeDefined();
            expect(Array.isArray(result.apps)).toBe(true);
        });

        it('应该能启动应用', async () => {
            const result = await adapter.execute('apps_launch', {
                name: 'Calculator'
            });

            expect(result).toBeDefined();
            expect(result.success).toBeDefined();
        });

        it('应该能关闭应用', async () => {
            const result = await adapter.execute('apps_close', {
                name: 'Calculator'
            });

            expect(result).toBeDefined();
            expect(result.success).toBeDefined();
        });

        it('应该能列出已安装的应用', async () => {
            const result = await adapter.execute('apps_list_installed', {});

            expect(result).toBeDefined();
            expect(Array.isArray(result.apps)).toBe(true);
        });

        it('应该拒绝空应用名', async () => {
            await expect(
                adapter.execute('apps_launch', { name: '' })
            ).rejects.toThrow();
        });

        it('应该拒绝启动危险应用', async () => {
            await expect(
                adapter.execute('apps_launch', { name: 'rm -rf /' })
            ).rejects.toThrow();
        });
    });
});
