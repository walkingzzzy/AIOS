/**
 * WeatherAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { WeatherAdapter } from '../../adapters/weather/WeatherAdapter';

describe('WeatherAdapter', () => {
    let adapter: WeatherAdapter;

    beforeEach(() => {
        adapter = new WeatherAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('weather');
            expect(adapter.name).toBe('Weather');
            expect(adapter.permissionLevel).toBe('public');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('weather_get_current');
            expect(toolNames).toContain('weather_get_forecast');
        });
    });

    describe('天气查询', () => {
        it('应该能获取当前天气', async () => {
            const result = await adapter.execute('weather_get_current', {
                location: 'Beijing'
            });

            expect(result).toBeDefined();
            expect(result.location).toBeDefined();
            expect(result.temperature).toBeDefined();
            expect(result.condition).toBeDefined();
        });

        it('应该能获取天气预报', async () => {
            const result = await adapter.execute('weather_get_forecast', {
                location: 'Shanghai',
                days: 3
            });

            expect(result).toBeDefined();
            expect(Array.isArray(result.forecast)).toBe(true);
            expect(result.forecast.length).toBeLessThanOrEqual(3);
        });

        it('应该拒绝空位置', async () => {
            await expect(
                adapter.execute('weather_get_current', { location: '' })
            ).rejects.toThrow();
        });

        it('应该拒绝无效的天数', async () => {
            await expect(
                adapter.execute('weather_get_forecast', {
                    location: 'Beijing',
                    days: 0
                })
            ).rejects.toThrow();

            await expect(
                adapter.execute('weather_get_forecast', {
                    location: 'Beijing',
                    days: 20
                })
            ).rejects.toThrow();
        });
    });
});
