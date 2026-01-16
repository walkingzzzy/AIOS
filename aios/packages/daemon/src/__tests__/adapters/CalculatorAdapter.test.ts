/**
 * CalculatorAdapter 单元测试
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { CalculatorAdapter } from '../../adapters/calculator/CalculatorAdapter';

describe('CalculatorAdapter', () => {
    let adapter: CalculatorAdapter;

    beforeEach(() => {
        adapter = new CalculatorAdapter();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('calculator');
            expect(adapter.name).toBe('Calculator');
            expect(adapter.permissionLevel).toBe('public');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('calculator_evaluate');
        });

        it('应该始终可用', async () => {
            const isAvailable = await adapter.isAvailable();
            expect(isAvailable).toBe(true);
        });
    });

    describe('数学计算', () => {
        it('应该能计算基本算术', async () => {
            const testCases = [
                { expression: '2 + 2', expected: 4 },
                { expression: '10 - 3', expected: 7 },
                { expression: '5 * 6', expected: 30 },
                { expression: '20 / 4', expected: 5 },
            ];

            for (const { expression, expected } of testCases) {
                const result = await adapter.execute('calculator_evaluate', { expression });
                expect(result.result).toBe(expected);
            }
        });

        it('应该能计算复杂表达式', async () => {
            const result = await adapter.execute('calculator_evaluate', {
                expression: '(2 + 3) * 4 - 10 / 2'
            });

            expect(result.result).toBe(15);
        });

        it('应该能使用数学函数', async () => {
            const result = await adapter.execute('calculator_evaluate', {
                expression: 'Math.sqrt(16)'
            });

            expect(result.result).toBe(4);
        });

        it('应该能处理小数', async () => {
            const result = await adapter.execute('calculator_evaluate', {
                expression: '0.1 + 0.2'
            });

            expect(result.result).toBeCloseTo(0.3);
        });

        it('应该拒绝无效表达式', async () => {
            await expect(
                adapter.execute('calculator_evaluate', { expression: 'invalid' })
            ).rejects.toThrow();
        });

        it('应该拒绝危险代码', async () => {
            await expect(
                adapter.execute('calculator_evaluate', { expression: 'process.exit()' })
            ).rejects.toThrow();
        });
    });
});
