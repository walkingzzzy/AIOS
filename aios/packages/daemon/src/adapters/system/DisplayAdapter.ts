/**
 * 显示控制适配器
 * 跨平台亮度控制
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 动态导入 brightness (ESM)
let brightness: {
    get: () => Promise<number>;
    set: (level: number) => Promise<void>;
};

export class DisplayAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.display';
    readonly name = '显示控制';
    readonly description = '跨平台亮度控制适配器';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'get_brightness',
            name: '获取亮度',
            description: '获取当前屏幕亮度 (0-100)',
            permissionLevel: 'public',
        },
        {
            id: 'set_brightness',
            name: '设置亮度',
            description: '设置屏幕亮度 (0-100)',
            permissionLevel: 'low',
            parameters: [
                { name: 'brightness', type: 'number', required: true, description: '亮度值 0-100' },
            ],
        },
    ];

    async initialize(): Promise<void> {
        const mod = await import('brightness');
        brightness = mod.default || mod;
    }

    async checkAvailability(): Promise<boolean> {
        try {
            await this.initialize();
            await brightness.get();
            return true;
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'get_brightness':
                    return this.getBrightness();
                case 'set_brightness':
                    return this.setBrightness(args.brightness as number);
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async getBrightness(): Promise<AdapterResult> {
        const level = await brightness.get();
        // brightness 返回 0-1，转换为 0-100
        return this.success({ brightness: Math.round(level * 100) });
    }

    private async setBrightness(level: number): Promise<AdapterResult> {
        // 转换 0-100 到 0-1
        const clamped = Math.max(0, Math.min(100, level));
        await brightness.set(clamped / 100);
        return this.success({ brightness: clamped });
    }
}

export const displayAdapter = new DisplayAdapter();
