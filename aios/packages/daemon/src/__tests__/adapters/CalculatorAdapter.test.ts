/**
 * CalculatorAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { CalculatorAdapter } from '../../adapters/calculator/CalculatorAdapter';

vi.mock('mathjs', () => ({
    evaluate: vi.fn((expression: string) => {
        if (expression === '2 + 2') {
            return 4;
        }
        return 42;
    }),
    format: vi.fn((value: unknown) => String(value)),
}));

describe('CalculatorAdapter', () => {
    let adapter: CalculatorAdapter;

    beforeEach(async () => {
        adapter = new CalculatorAdapter();
        await adapter.initialize();
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.calculator');
            expect(adapter.name).toBe('计算器');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('calculate');
            expect(capabilityIds).toContain('convert');
        });
    });

    describe('计算与转换', () => {
        it('应该能计算表达式', async () => {
            const result = await adapter.invoke('calculate', { expression: '2 + 2' });

            expect(result.success).toBe(true);
            expect((result.data as { numericResult?: number }).numericResult).toBe(4);
        });

        it('应该能进行单位转换', async () => {
            const result = await adapter.invoke('convert', {
                value: 1,
                fromUnit: 'm',
                toUnit: 'cm',
            });

            expect(result.success).toBe(true);
        });

        it('应该拒绝空表达式', async () => {
            const result = await adapter.invoke('calculate', { expression: '' });
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('INVALID_ARGS');
        });
    });
});
