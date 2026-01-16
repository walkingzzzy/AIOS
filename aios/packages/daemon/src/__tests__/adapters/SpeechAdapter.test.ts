/**
 * SpeechAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { SpeechAdapter } from '../../adapters/speech/SpeechAdapter';

describe('SpeechAdapter', () => {
    let adapter: SpeechAdapter;

    beforeEach(() => {
        adapter = new SpeechAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('speech');
            expect(adapter.name).toBe('Text-to-Speech');
            expect(adapter.permissionLevel).toBe('low');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('speech_speak');
            expect(toolNames).toContain('speech_stop');
        });
    });

    describe('语音合成', () => {
        it('应该能朗读文本', async () => {
            const result = await adapter.execute('speech_speak', {
                text: 'Hello World'
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能设置语音参数', async () => {
            const result = await adapter.execute('speech_speak', {
                text: 'Test',
                voice: 'en-US',
                rate: 1.5,
                volume: 0.8
            });

            expect(result).toBeDefined();
            expect(result.success).toBe(true);
        });

        it('应该能停止朗读', async () => {
            await adapter.execute('speech_speak', { text: 'Long text...' });

            const result = await adapter.execute('speech_stop', {});
            expect(result.success).toBe(true);
        });

        it('应该拒绝空文本', async () => {
            await expect(
                adapter.execute('speech_speak', { text: '' })
            ).rejects.toThrow();
        });

        it('应该拒绝无效的速率', async () => {
            await expect(
                adapter.execute('speech_speak', {
                    text: 'Test',
                    rate: 5.0
                })
            ).rejects.toThrow();
        });
    });
});
