/**
 * 语音适配器
 * 跨平台 TTS 语音播放
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 动态导入 say (ESM)
let sayModule: any;

export class SpeechAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.speech';
    readonly name = '语音播放';
    readonly description = '跨平台 TTS 语音播放适配器';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'speak',
            name: '朗读文本',
            description: '将文本转换为语音并播放',
            permissionLevel: 'low',
            parameters: [
                { name: 'text', type: 'string', required: true, description: '要朗读的文本' },
                { name: 'voice', type: 'string', required: false, description: '语音名称' },
                { name: 'speed', type: 'number', required: false, description: '语速 (0.5-2.0)' },
            ],
        },
        {
            id: 'stop',
            name: '停止播放',
            description: '停止当前语音播放',
            permissionLevel: 'low',
        },
        {
            id: 'get_voices',
            name: '获取语音列表',
            description: '获取系统已安装的语音列表',
            permissionLevel: 'public',
        },
    ];

    async initialize(): Promise<void> {
        const mod = await import('say');
        sayModule = mod.default || mod;
    }

    async checkAvailability(): Promise<boolean> {
        try {
            await this.initialize();
            return true;
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'speak':
                    return this.speak(
                        args.text as string,
                        args.voice as string | undefined,
                        args.speed as number | undefined
                    );
                case 'stop':
                    return this.stopSpeaking();
                case 'get_voices':
                    return this.getVoices();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private speak(text: string, voice?: string, speed?: number): Promise<AdapterResult> {
        return new Promise((resolve) => {
            if (!text) {
                resolve(this.failure('INVALID_ARGS', '文本不能为空'));
                return;
            }

            const speechSpeed = speed ?? 1.0;
            const clampedSpeed = Math.max(0.5, Math.min(2.0, speechSpeed));

            sayModule.speak(text, voice, clampedSpeed, (err: Error | null) => {
                if (err) {
                    console.error('[SpeechAdapter] speak failed:', err);
                    resolve(this.failure('SPEAK_FAILED', err.message));
                } else {
                    resolve(this.success({ text, voice, speed: clampedSpeed }));
                }
            });
        });
    }

    private stopSpeaking(): AdapterResult {
        try {
            sayModule.stop();
            return this.success({ stopped: true });
        } catch (error) {
            return this.failure('STOP_FAILED', String(error));
        }
    }

    private getVoices(): Promise<AdapterResult> {
        return new Promise((resolve) => {
            sayModule.getInstalledVoices((err: Error | null, voices: string[]) => {
                if (err) {
                    console.error('[SpeechAdapter] getVoices failed:', err);
                    resolve(this.failure('GET_VOICES_FAILED', err.message));
                } else {
                    resolve(this.success({ voices: voices || [] }));
                }
            });
        });
    }
}

export const speechAdapter = new SpeechAdapter();
