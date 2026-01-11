/**
 * 音频控制适配器
 * 跨平台音量控制
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 动态导入 loudness (ESM)
let loudness: {
    getVolume: () => Promise<number>;
    setVolume: (volume: number) => Promise<void>;
    getMuted: () => Promise<boolean>;
    setMuted: (muted: boolean) => Promise<void>;
};

export class AudioAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.audio';
    readonly name = '音频控制';
    readonly description = '跨平台音量控制适配器';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'get_volume',
            name: '获取音量',
            description: '获取当前系统音量 (0-100)',
            permissionLevel: 'public',
        },
        {
            id: 'set_volume',
            name: '设置音量',
            description: '设置系统音量 (0-100)',
            permissionLevel: 'low',
            parameters: [
                { name: 'volume', type: 'number', required: true, description: '音量值 0-100' },
            ],
        },
        {
            id: 'get_muted',
            name: '获取静音状态',
            description: '检查是否静音',
            permissionLevel: 'public',
        },
        {
            id: 'set_muted',
            name: '设置静音',
            description: '设置静音状态',
            permissionLevel: 'low',
            parameters: [
                { name: 'muted', type: 'boolean', required: true, description: '是否静音' },
            ],
        },
        {
            id: 'toggle_mute',
            name: '切换静音',
            description: '切换静音状态',
            permissionLevel: 'low',
        },
    ];

    async initialize(): Promise<void> {
        const mod = await import('loudness');
        loudness = mod.default || mod;
    }

    async checkAvailability(): Promise<boolean> {
        try {
            await this.initialize();
            await loudness.getVolume();
            return true;
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'get_volume':
                    return this.getVolume();
                case 'set_volume':
                    return this.setVolume(args.volume as number);
                case 'get_muted':
                    return this.getMuted();
                case 'set_muted':
                    return this.setMuted(args.muted as boolean);
                case 'toggle_mute':
                    return this.toggleMute();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async getVolume(): Promise<AdapterResult> {
        const volume = await loudness.getVolume();
        return this.success({ volume });
    }

    private async setVolume(volume: number): Promise<AdapterResult> {
        const clamped = Math.max(0, Math.min(100, volume));
        await loudness.setVolume(clamped);
        return this.success({ volume: clamped });
    }

    private async getMuted(): Promise<AdapterResult> {
        const muted = await loudness.getMuted();
        return this.success({ muted });
    }

    private async setMuted(muted: boolean): Promise<AdapterResult> {
        await loudness.setMuted(muted);
        return this.success({ muted });
    }

    private async toggleMute(): Promise<AdapterResult> {
        const current = await loudness.getMuted();
        await loudness.setMuted(!current);
        return this.success({ muted: !current });
    }
}

export const audioAdapter = new AudioAdapter();
