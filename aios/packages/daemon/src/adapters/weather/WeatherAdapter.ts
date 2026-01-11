/**
 * 天气适配器
 * 使用 OpenWeatherMap API 查询天气
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

interface WeatherInfo {
    temp: number;
    feels_like: number;
    description: string;
    humidity: number;
    wind_speed: number;
    city: string;
}

export class WeatherAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.weather';
    readonly name = '天气';
    readonly description = '天气查询适配器 (OpenWeatherMap API)';

    private apiKey: string = '';
    private baseUrl = 'https://api.openweathermap.org/data/2.5';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'get_current_weather',
            name: '获取当前天气',
            description: '查询指定城市的当前天气',
            permissionLevel: 'public',
            parameters: [
                { name: 'city', type: 'string', required: true, description: '城市名称' },
            ],
        },
        {
            id: 'get_forecast',
            name: '获取天气预报',
            description: '获取未来几天的天气预报',
            permissionLevel: 'public',
            parameters: [
                { name: 'city', type: 'string', required: true, description: '城市名称' },
                { name: 'days', type: 'number', required: false, description: '天数 (默认5)' },
            ],
        },
        {
            id: 'set_api_key',
            name: '设置 API Key',
            description: '配置 OpenWeatherMap API Key',
            permissionLevel: 'medium',
            parameters: [
                { name: 'apiKey', type: 'string', required: true, description: 'API Key' },
            ],
        },
    ];

    async initialize(): Promise<void> {
        // 从环境变量读取 API Key
        this.apiKey = process.env.OPENWEATHERMAP_API_KEY || '';
    }

    async checkAvailability(): Promise<boolean> {
        return true; // 即使没有 API Key 也可用，只是查询会失败
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'get_current_weather':
                    return this.getCurrentWeather(args.city as string);
                case 'get_forecast':
                    return this.getForecast(args.city as string, args.days as number);
                case 'set_api_key':
                    return this.setApiKey(args.apiKey as string);
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async getCurrentWeather(city: string): Promise<AdapterResult> {
        if (!city) {
            return this.failure('INVALID_ARGS', '城市名称是必需的');
        }

        if (!this.apiKey) {
            return this.failure('API_KEY_MISSING', '请先配置 OpenWeatherMap API Key');
        }

        try {
            const url = `${this.baseUrl}/weather?q=${encodeURIComponent(city)}&appid=${this.apiKey}&units=metric&lang=zh_cn`;
            const response = await fetch(url);

            if (!response.ok) {
                if (response.status === 401) {
                    return this.failure('INVALID_API_KEY', 'API Key 无效');
                }
                if (response.status === 404) {
                    return this.failure('CITY_NOT_FOUND', `城市 "${city}" 未找到`);
                }
                return this.failure('API_ERROR', `API 错误: ${response.status}`);
            }

            const data = await response.json() as any;

            const weather: WeatherInfo = {
                temp: Math.round(data.main.temp),
                feels_like: Math.round(data.main.feels_like),
                description: data.weather[0].description,
                humidity: data.main.humidity,
                wind_speed: data.wind.speed,
                city: data.name,
            };

            return this.success({ weather });
        } catch (error) {
            return this.failure('NETWORK_ERROR', `网络错误: ${error}`);
        }
    }

    private async getForecast(city: string, days?: number): Promise<AdapterResult> {
        if (!city) {
            return this.failure('INVALID_ARGS', '城市名称是必需的');
        }

        if (!this.apiKey) {
            return this.failure('API_KEY_MISSING', '请先配置 OpenWeatherMap API Key');
        }

        const numDays = days || 5;

        try {
            const url = `${this.baseUrl}/forecast?q=${encodeURIComponent(city)}&appid=${this.apiKey}&units=metric&lang=zh_cn`;
            const response = await fetch(url);

            if (!response.ok) {
                return this.failure('API_ERROR', `API 错误: ${response.status}`);
            }

            const data = await response.json() as any;

            // 每3小时一条，取每天中午的数据
            const dailyForecast = data.list
                .filter((_: any, index: number) => index % 8 === 4) // 大约中午12点
                .slice(0, numDays)
                .map((item: any) => ({
                    date: item.dt_txt.split(' ')[0],
                    temp: Math.round(item.main.temp),
                    description: item.weather[0].description,
                    humidity: item.main.humidity,
                }));

            return this.success({ city: data.city.name, forecast: dailyForecast });
        } catch (error) {
            return this.failure('NETWORK_ERROR', `网络错误: ${error}`);
        }
    }

    private setApiKey(apiKey: string): AdapterResult {
        if (!apiKey) {
            return this.failure('INVALID_ARGS', 'API Key 不能为空');
        }

        this.apiKey = apiKey;
        return this.success({ configured: true });
    }
}

export const weatherAdapter = new WeatherAdapter();
