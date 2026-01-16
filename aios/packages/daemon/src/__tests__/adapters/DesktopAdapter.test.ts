/**
 * DesktopAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { DesktopAdapter } from '../../adapters/system/DesktopAdapter';

describe('DesktopAdapter', () => {
    let adapter: DesktopAdapter;

    beforeEach(() => {
        adapter = new DesktopAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('desktop');
            expect(adapter.name).toBe('Desktop Control');
            expect(adapter.permissionLevel).toBe('medium');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('desktop_set_wallpaper');
            expect(toolNames).toContain('desktop_get_appearance');
            expect(toolNames).toContain('desktop_set_appearance');
        });
    });

    describe('桌面控制', () => {
        it('应该能设置壁纸', async () => {
            const result = await adapter.execute('desktop_set_wallpaper', {
                path: '/path/to/wallpaper.jpg'
            });

            expect(result).toBeDefined();
            expect(result.success).toBeDefined();
        });

        it('应该能获取外观模式', async () => {
            const result = await adapter.execute('desktop_get_appearance', {});

            expect(result).toBeDefined();
            expect(result.mode).toBeDefined();
            expect(['light', 'dark', 'auto']).toContain(result.mode);
        });

        it('应该能设置外观模式', async () => {
            const result = await adapter.execute('desktop_set_appearance', {
                mode: 'dark'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能模拟点击', async () => {
            const result = await adapter.execute('desktop_click', {
                x: 100,
                y: 200
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能模拟输入', async () => {
            const result = await adapter.execute('desktop_type', {
                text: 'Hello World'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该拒绝无效的外观模式', async () => {
            await expect(
                adapter.execute('desktop_set_appearance', { mode: 'invalid' })
            ).rejects.toThrow();
        });

        it('应该拒绝无效的坐标', async () => {
            await expect(
                adapter.execute('desktop_click', { x: -100, y: 200 })
            ).rejects.toThrow();
        });
    });
});
