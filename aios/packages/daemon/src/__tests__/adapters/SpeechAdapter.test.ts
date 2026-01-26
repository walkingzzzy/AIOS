/**
 * SpeechAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { SpeechAdapter } from '../../adapters/speech/SpeechAdapter';

vi.mock('say', () => ({
    default: {
        speak: vi.fn((_: string, __: string | undefined, ___: number | undefined, cb?: (err: Error | null) => void) => {
            cb?.(null);
        }),
        stop: vi.fn(),
        getInstalledVoices: vi.fn((cb?: (err: Error | null, voices: string[]) => void) => {
            cb?.(null, ['Voice A']);
        }),
    },
}));

describe('SpeechAdapter', () => {
    let adapter: SpeechAdapter;

    beforeEach(async () => {
        adapter = new SpeechAdapter();
        await adapter.initialize();
        process.env.GOOGLE_SPEECH_API_KEY = 'test-key';
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: true,
            json: async () => ({
                results: [
                    { alternatives: [{ transcript: '你好', confidence: 0.88 }] },
                ],
            }),
        })));
    });

    afterEach(() => {
        delete process.env.GOOGLE_SPEECH_API_KEY;
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.speech');
            expect(adapter.name).toBe('语音交互');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('speak');
            expect(capabilityIds).toContain('stop');
            expect(capabilityIds).toContain('get_voices');
            expect(capabilityIds).toContain('transcribe');
            expect(capabilityIds).toContain('set_stt_api_key');
        });
    });

    describe('语音合成', () => {
        it('应该能朗读文本', async () => {
            const result = await adapter.invoke('speak', {
                text: 'Hello World',
            });

            expect(result.success).toBe(true);
            expect((result.data as { text?: string }).text).toBe('Hello World');
        });

        it('应该能设置语音参数', async () => {
            const result = await adapter.invoke('speak', {
                text: 'Test',
                voice: 'en-US',
                speed: 1.5,
            });

            expect(result.success).toBe(true);
            expect((result.data as { voice?: string }).voice).toBe('en-US');
        });

        it('应该能停止朗读', async () => {
            const result = await adapter.invoke('stop', {});
            expect(result.success).toBe(true);
        });

        it('应该拒绝空文本', async () => {
            const result = await adapter.invoke('speak', { text: '' });
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('INVALID_ARGS');
        });

        it('应该限制速率范围', async () => {
            const result = await adapter.invoke('speak', {
                text: 'Test',
                speed: 5.0,
            });

            expect(result.success).toBe(true);
            expect((result.data as { speed?: number }).speed).toBe(2.0);
        });

        it('应该能获取语音列表', async () => {
            const result = await adapter.invoke('get_voices', {});

            expect(result.success).toBe(true);
            const voices = (result.data as { voices?: unknown[] }).voices;
            expect(Array.isArray(voices)).toBe(true);
            expect(voices?.length).toBeGreaterThan(0);
        });

        it('应该能识别语音内容', async () => {
            const result = await adapter.invoke('transcribe', {
                audioContent: 'dGVzdA==',
                languageCode: 'zh-CN',
            });

            expect(result.success).toBe(true);
            const transcripts = (result.data as { transcripts?: Array<{ transcript?: string }> }).transcripts;
            expect(Array.isArray(transcripts)).toBe(true);
            expect(transcripts?.[0]?.transcript).toBe('你好');
        });
    });
});
