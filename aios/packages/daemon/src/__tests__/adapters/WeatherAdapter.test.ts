/**
 * WeatherAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { WeatherAdapter } from '../../adapters/weather/WeatherAdapter';

describe('WeatherAdapter', () => {
    let adapter: WeatherAdapter;

    beforeEach(() => {
        adapter = new WeatherAdapter();
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true,
            status: 200,
            json: async () => ({
                main: { temp: 20, feels_like: 18, humidity: 60 },
                weather: [{ description: '晴' }],
                wind: { speed: 2 },
                name: 'Beijing',
                list: Array.from({ length: 16 }).map((_, index) => ({
                    dt_txt: `2024-01-0${Math.floor(index / 8) + 1} 12:00:00`,
                    main: { temp: 20 + index, humidity: 50 },
                    weather: [{ description: '晴' }],
                })),
                city: { name: 'Beijing' },
            }),
        })));
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.weather');
            expect(adapter.name).toBe('天气');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的工具列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('get_current_weather');
            expect(capabilityIds).toContain('get_forecast');
            expect(capabilityIds).toContain('set_api_key');
        });
    });

    describe('天气查询', () => {
        it('应该能获取当前天气', async () => {
            await adapter.invoke('set_api_key', { apiKey: 'test-key' });
            const result = await adapter.invoke('get_current_weather', {
                city: 'Beijing',
            });

            expect(result.success).toBe(true);
            expect((result.data as { weather?: unknown }).weather).toBeDefined();
        });

        it('应该能获取天气预报', async () => {
            await adapter.invoke('set_api_key', { apiKey: 'test-key' });
            const result = await adapter.invoke('get_forecast', {
                city: 'Shanghai',
                days: 3,
            });

            expect(result.success).toBe(true);
            const forecast = (result.data as { forecast?: unknown[] }).forecast;
            expect(Array.isArray(forecast)).toBe(true);
        });

        it('应该拒绝空位置', async () => {
            const result = await adapter.invoke('get_current_weather', { city: '' });
            expect(result.success).toBe(false);
        });

        it('缺少 API Key 时应该返回错误', async () => {
            const result = await adapter.invoke('get_current_weather', { city: 'Beijing' });
            expect(result.success).toBe(false);
        });
    });
});
