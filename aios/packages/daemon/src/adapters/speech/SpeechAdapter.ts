/**
 * 语音适配器
 * 跨平台 TTS 语音播放 + STT 语音识别
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 动态导入 say (ESM)
let sayModule: any;

export class SpeechAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.speech';
    readonly name = '语音交互';
    readonly description = '跨平台 TTS 语音播放与 STT 语音识别';

    private sttApiKey = '';
    private sttEndpoint = 'https://speech.googleapis.com/v1/speech:recognize';

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
        {
            id: 'transcribe',
            name: '语音识别',
            description: '将音频内容识别为文本',
            permissionLevel: 'medium',
            parameters: [
                { name: 'audioContent', type: 'string', required: true, description: 'Base64 编码的音频内容' },
                { name: 'languageCode', type: 'string', required: false, description: '语言代码 (默认 zh-CN)' },
                { name: 'sampleRateHertz', type: 'number', required: false, description: '采样率 (Hz)' },
                { name: 'encoding', type: 'string', required: false, description: '音频编码 (LINEAR16/FLAC/MP3/WEBM_OPUS 等)' },
                { name: 'enableAutomaticPunctuation', type: 'boolean', required: false, description: '是否自动添加标点' },
                { name: 'model', type: 'string', required: false, description: '模型 (default/command_and_search 等)' },
            ],
        },
        {
            id: 'set_stt_api_key',
            name: '设置 STT API Key',
            description: '配置 Google Speech API Key',
            permissionLevel: 'medium',
            parameters: [
                { name: 'apiKey', type: 'string', required: true, description: 'API Key' },
            ],
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
                case 'transcribe':
                    return this.transcribe(args);
                case 'set_stt_api_key':
                    return this.setSttApiKey(args.apiKey as string);
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

    private ensureSttApiKey(): string | null {
        if (!this.sttApiKey) {
            this.sttApiKey = process.env.GOOGLE_SPEECH_API_KEY || '';
        }
        return this.sttApiKey || null;
    }

    private async transcribe(args: Record<string, unknown>): Promise<AdapterResult> {
        const audioContent = args.audioContent as string;
        if (!audioContent) {
            return this.failure('INVALID_ARGS', '音频内容不能为空');
        }

        const apiKey = this.ensureSttApiKey();
        if (!apiKey) {
            return this.failure('API_KEY_MISSING', '请先配置 Google Speech API Key');
        }

        const languageCode = (args.languageCode as string) || 'zh-CN';
        const encoding = (args.encoding as string) || 'LINEAR16';
        const sampleRateHertz = args.sampleRateHertz as number | undefined;
        const enableAutomaticPunctuation = args.enableAutomaticPunctuation as boolean | undefined;
        const model = args.model as string | undefined;

        const config: Record<string, unknown> = {
            languageCode,
            encoding,
            ...(sampleRateHertz ? { sampleRateHertz } : {}),
            ...(enableAutomaticPunctuation !== undefined ? { enableAutomaticPunctuation } : {}),
            ...(model ? { model } : {}),
        };

        try {
            const url = `${this.sttEndpoint}?key=${encodeURIComponent(apiKey)}`;
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    config,
                    audio: { content: audioContent },
                }),
            });

            if (!response.ok) {
                return this.failure('STT_ERROR', `API 错误: ${response.status}`);
            }

            const data = await response.json() as {
                results?: Array<{
                    alternatives?: Array<{ transcript?: string; confidence?: number }>;
                }>;
            };

            const transcripts = (data.results ?? [])
                .flatMap((result) => result.alternatives ?? [])
                .filter((alt) => alt.transcript)
                .map((alt) => ({
                    transcript: alt.transcript as string,
                    confidence: alt.confidence ?? null,
                }));

            return this.success({
                transcripts,
                best: transcripts[0] ?? null,
            });
        } catch (error) {
            return this.failure('NETWORK_ERROR', `网络错误: ${String(error)}`);
        }
    }

    private setSttApiKey(apiKey: string): AdapterResult {
        if (!apiKey) {
            return this.failure('INVALID_ARGS', 'API Key 不能为空');
        }

        this.sttApiKey = apiKey;
        return this.success({ configured: true });
    }
}

export const speechAdapter = new SpeechAdapter();
