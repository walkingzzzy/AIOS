/**
 * TranslateAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TranslateAdapter } from '../../adapters/translate/TranslateAdapter';

describe('TranslateAdapter', () => {
    let adapter: TranslateAdapter;

    beforeEach(() => {
        adapter = new TranslateAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('translate');
            expect(adapter.name).toBe('Translation');
            expect(adapter.permissionLevel).toBe('public');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('translate_text');
            expect(toolNames).toContain('translate_detect_language');
        });
    });

    describe('翻译功能', () => {
        it('应该能翻译文本', async () => {
            const result = await adapter.execute('translate_text', {
                text: 'Hello',
                from: 'en',
                to: 'zh'
            });

            expect(result).toBeDefined();
            expect(result.translatedText).toBeDefined();
            expect(typeof result.translatedText).toBe('string');
        });

        it('应该能自动检测源语言', async () => {
            const result = await adapter.execute('translate_text', {
                text: 'Hello',
                to: 'zh'
            });

            expect(result).toBeDefined();
            expect(result.translatedText).toBeDefined();
        });

        it('应该能检测语言', async () => {
            const result = await adapter.execute('translate_detect_language', {
                text: 'Hello World'
            });

            expect(result).toBeDefined();
            expect(result.language).toBeDefined();
            expect(typeof result.language).toBe('string');
        });

        it('应该拒绝空文本', async () => {
            await expect(
                adapter.execute('translate_text', {
                    text: '',
                    to: 'zh'
                })
            ).rejects.toThrow();
        });

        it('应该拒绝无效的语言代码', async () => {
            await expect(
                adapter.execute('translate_text', {
                    text: 'Hello',
                    to: 'invalid'
                })
            ).rejects.toThrow();
        });
    });
});
