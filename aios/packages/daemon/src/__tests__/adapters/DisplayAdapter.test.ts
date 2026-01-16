/**
 * DisplayAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { DisplayAdapter } from '../../adapters/system/DisplayAdapter';

describe('DisplayAdapter', () => {
    let adapter: DisplayAdapter;

    beforeEach(() => {
        adapter = new DisplayAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('display');
            expect(adapter.name).toBe('Display Control');
            expect(adapter.description).toContain('brightness');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('display_set_brightness');
            expect(toolNames).toContain('display_get_brightness');
        });

        it('应该正确检查可用性', async () => {
            const isAvailable = await adapter.isAvailable();
            expect(typeof isAvailable).toBe('boolean');
        });
    });

    describe('亮度控制', () => {
        it('应该能设置亮度', async () => {
            const result = await adapter.execute('display_set_brightness', {
                level: 50
            });

            expect(result).toBeDefined();
            expect(result.success).toBeDefined();
        });

        it('应该拒绝无效的亮度值', async () => {
            await expect(
                adapter.execute('display_set_brightness', { level: 150 })
            ).rejects.toThrow();

            await expect(
                adapter.execute('display_set_brightness', { level: -10 })
            ).rejects.toThrow();
        });

        it('应该能获取当前亮度', async () => {
            const result = await adapter.execute('display_get_brightness', {});

            expect(result).toBeDefined();
            expect(typeof result.level).toBe('number');
            expect(result.level).toBeGreaterThanOrEqual(0);
            expect(result.level).toBeLessThanOrEqual(100);
        });
    });

    describe('错误处理', () => {
        it('应该处理未知工具', async () => {
            await expect(
                adapter.execute('unknown_tool', {})
            ).rejects.toThrow();
        });

        it('应该处理缺少参数', async () => {
            await expect(
                adapter.execute('display_set_brightness', {})
            ).rejects.toThrow();
        });
    });
});
