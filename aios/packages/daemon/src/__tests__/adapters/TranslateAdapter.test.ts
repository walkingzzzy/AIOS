/**
 * TranslateAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TranslateAdapter } from '../../adapters/translate/TranslateAdapter';

describe('TranslateAdapter', () => {
    let adapter: TranslateAdapter;

    beforeEach(() => {
        adapter = new TranslateAdapter();
        process.env.GOOGLE_TRANSLATE_API_KEY = 'test-key';
        vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo) => {
            const url = typeof input === 'string' ? input : input.toString();
            if (url.includes('/detect')) {
                return {
                    ok: true,
                    json: async () => ({
                        data: {
                            detections: [[{ language: 'en', confidence: 0.9 }]],
                        },
                    }),
                } as Response;
            }
            if (url.includes('/languages')) {
                return {
                    ok: true,
                    json: async () => ({
                        data: {
                            languages: [{ language: 'en', name: '英语' }],
                        },
                    }),
                } as Response;
            }
            return {
                ok: true,
                json: async () => ({
                    data: { translations: [{ translatedText: '你好', detectedSourceLanguage: 'en' }] },
                }),
            } as Response;
        }));
    });

    afterEach(() => {
        delete process.env.GOOGLE_TRANSLATE_API_KEY;
        vi.unstubAllGlobals();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.translate');
            expect(adapter.name).toBe('翻译');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的工具列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('translate');
            expect(capabilityIds).toContain('detect_language');
            expect(capabilityIds).toContain('get_languages');
        });
    });

    describe('翻译功能', () => {
        it('应该能翻译文本', async () => {
            const result = await adapter.invoke('translate', {
                text: 'Hello',
                sourceLang: 'en',
                targetLang: 'zh',
            });

            expect(result.success).toBe(true);
            expect((result.data as { translatedText?: string }).translatedText).toBeDefined();
        });

        it('应该能自动检测源语言', async () => {
            const result = await adapter.invoke('translate', {
                text: 'Hello',
                targetLang: 'zh',
            });

            expect(result.success).toBe(true);
            expect((result.data as { translatedText?: string }).translatedText).toBeDefined();
        });

        it('应该能检测语言', async () => {
            const result = await adapter.invoke('detect_language', {
                text: 'Hello World'
            });

            expect(result.success).toBe(true);
            expect((result.data as { language?: string }).language).toBeDefined();
        });

        it('应该拒绝空文本', async () => {
            const result = await adapter.invoke('translate', {
                text: '',
                targetLang: 'zh',
            });
            expect(result.success).toBe(false);
        });
    });
});
