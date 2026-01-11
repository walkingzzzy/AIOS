/**
 * 计算器适配器
 * 数学计算和单位转换
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// mathjs 类型
let mathEvaluate: (expression: string) => unknown;
let mathFormat: (value: unknown, options?: { precision?: number }) => string;

export class CalculatorAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.calculator';
    readonly name = '计算器';
    readonly description = '数学计算和单位转换适配器';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'calculate',
            name: '计算表达式',
            description: '计算数学表达式',
            permissionLevel: 'public',
            parameters: [
                {
                    name: 'expression',
                    type: 'string',
                    required: true,
                    description: '数学表达式，如 "2 + 2 * 3"',
                },
            ],
        },
        {
            id: 'convert',
            name: '单位转换',
            description: '进行单位转换',
            permissionLevel: 'public',
            parameters: [
                { name: 'value', type: 'number', required: true, description: '数值' },
                { name: 'fromUnit', type: 'string', required: true, description: '源单位' },
                { name: 'toUnit', type: 'string', required: true, description: '目标单位' },
            ],
        },
    ];

    async initialize(): Promise<void> {
        const math = await import('mathjs');
        mathEvaluate = math.evaluate;
        mathFormat = math.format;
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
                case 'calculate':
                    return this.calculate(args.expression as string);
                case 'convert':
                    return this.convert(
                        args.value as number,
                        args.fromUnit as string,
                        args.toUnit as string
                    );
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private calculate(expression: string): AdapterResult {
        if (!expression) {
            return this.failure('INVALID_ARGS', '表达式不能为空');
        }

        try {
            const result = mathEvaluate(expression);
            const formatted = mathFormat(result, { precision: 14 });

            return this.success({
                expression,
                result: formatted,
                numericResult: typeof result === 'number' ? result : undefined,
            });
        } catch (error) {
            return this.failure('CALCULATION_ERROR', `计算错误: ${error}`);
        }
    }

    private convert(value: number, fromUnit: string, toUnit: string): AdapterResult {
        if (value === undefined || !fromUnit || !toUnit) {
            return this.failure('INVALID_ARGS', '数值和单位都是必需的');
        }

        try {
            const expression = `${value} ${fromUnit} to ${toUnit}`;
            const result = mathEvaluate(expression);
            const formatted = mathFormat(result, { precision: 14 });

            return this.success({
                value,
                fromUnit,
                toUnit,
                result: formatted,
            });
        } catch (error) {
            return this.failure('CONVERSION_ERROR', `转换错误: ${error}`);
        }
    }
}

export const calculatorAdapter = new CalculatorAdapter();
