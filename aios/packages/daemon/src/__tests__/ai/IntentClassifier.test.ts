/**
 * IntentClassifier 单元测试
 */

import { describe, it, expect } from 'vitest';
import { IntentClassifier } from '../../ai/IntentClassifier.js';

describe('IntentClassifier', () => {
    const classifier = new IntentClassifier();

    describe('简单指令分类', () => {
        it('应该识别音量控制指令', () => {
            const result = classifier.classify('把音量调到50');
            expect(result.type).toBe('simple');
            expect(result.confidence).toBeGreaterThan(0.5);
        });

        it('应该识别亮度控制指令', () => {
            const result = classifier.classify('亮度调低一点');
            expect(result.type).toBe('simple');
        });

        it('应该识别静音指令', () => {
            const result = classifier.classify('静音');
            expect(result.type).toBe('simple');
        });

        it('应该识别打开应用指令', () => {
            const result = classifier.classify('打开 Chrome');
            expect(result.type).toBe('simple');
        });

        it('应该识别关闭应用指令', () => {
            const result = classifier.classify('关闭微信');
            expect(result.type).toBe('simple');
        });

        it('应该识别锁屏指令', () => {
            const result = classifier.classify('锁屏');
            expect(result.type).toBe('simple');
        });

        it('应该识别关机指令', () => {
            const result = classifier.classify('关机');
            expect(result.type).toBe('simple');
        });

        it('应该识别英文指令', () => {
            const result = classifier.classify('set volume to 50');
            expect(result.type).toBe('simple');
        });
    });

    describe('视觉任务分类', () => {
        it('应该识别截图请求', () => {
            const result = classifier.classify('帮我截图');
            expect(result.type).toBe('visual');
        });

        it('应该识别屏幕分析请求', () => {
            const result = classifier.classify('看看屏幕上显示了什么');
            expect(result.type).toBe('visual');
        });

        it('应该识别界面查看请求', () => {
            const result = classifier.classify('当前界面是什么');
            expect(result.type).toBe('visual');
        });

        it('应该识别英文视觉请求', () => {
            const result = classifier.classify('take a screenshot');
            expect(result.type).toBe('visual');
        });
    });

    describe('复杂任务分类', () => {
        it('应该识别分析请求', () => {
            const result = classifier.classify('分析一下这段代码的问题');
            expect(result.type).toBe('complex');
        });

        it('应该识别总结请求', () => {
            const result = classifier.classify('总结一下今天的工作');
            expect(result.type).toBe('complex');
        });

        it('应该识别代码生成请求', () => {
            const result = classifier.classify('写一个排序算法');
            expect(result.type).toBe('complex');
        });

        it('应该识别多步骤任务', () => {
            const result = classifier.classify('分析一下这个问题，然后给我一个解决方案');
            expect(result.type).toBe('complex');
        });

        it('应该识别解释请求', () => {
            const result = classifier.classify('解释一下这个错误是什么意思');
            expect(result.type).toBe('complex');
        });
    });

    describe('默认分类', () => {
        it('短输入应该默认为简单任务', () => {
            const result = classifier.classify('你好');
            expect(result.type).toBe('simple');
            expect(result.confidence).toBeLessThanOrEqual(0.5);
        });

        it('长输入应该默认为复杂任务', () => {
            const result = classifier.classify('这是一段很长的文本，包含了很多内容，需要进行深入的处理和分析，可能涉及到多个步骤的操作');
            expect(result.type).toBe('complex');
        });
    });

    describe('置信度', () => {
        it('匹配多个关键词应该有更高的置信度', () => {
            const result1 = classifier.classify('音量');
            const result2 = classifier.classify('把音量调到50');
            expect(result2.confidence).toBeGreaterThanOrEqual(result1.confidence);
        });

        it('视觉任务应该有较高置信度', () => {
            const result = classifier.classify('截图');
            expect(result.confidence).toBeGreaterThan(0.5);
        });
    });
});
