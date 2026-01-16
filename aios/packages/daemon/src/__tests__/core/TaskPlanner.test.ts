/**
 * TaskPlanner 单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TaskPlanner } from '../../core/TaskPlanner.js';
import type { IAIEngine, InternalToolDefinition } from '@aios/shared';
import type { ExecutionStep, StepResult } from '../../types/orchestrator.js';

//创建 mock AI Engine
function createMockSmartEngine(): IAIEngine {return {
        name: 'smart-engine',
        chat: vi.fn().mockResolvedValue({ content: '' }),
        chatWithTools: vi.fn().mockResolvedValue({ content: '', toolCalls: [] }),
        chatStream: vi.fn(),
        chatStreamWithTools: vi.fn(),
    } as unknown as IAIEngine;
}

// 创建 mock 工具列表
function createMockTools(): InternalToolDefinition[] {
    return [
        { name: 'audio_set_volume', description: '设置音量', parameters: { type: 'object', properties: {} } },
        { name: 'apps_open_app', description: '打开应用', parameters: { type: 'object', properties: {} } },
        { name: 'power_lock_screen', description: '锁屏', parameters: { type: 'object', properties: {} } },
    ];
}

describe('TaskPlanner', () => {
    let planner: TaskPlanner;
    let mockEngine: IAIEngine;
    let mockTools: InternalToolDefinition[];

    beforeEach(() => {
        mockEngine = createMockSmartEngine();
        planner = new TaskPlanner(mockEngine);
        mockTools = createMockTools();
    });

    describe('JSON 提取', () => {
        it('应该从 markdown 代码块提取 JSON', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '```json\n{"goal": "测试任务", "steps": []}\n```',});

            const plan = await planner.planTask('测试任务', mockTools);
            
            expect(plan.goal).toBe('测试任务');
            expect(plan.steps).toEqual([]);
        });

        it('应该从纯 JSON 字符串提取', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '{"goal": "测试任务", "steps": []}',
            });

            const plan = await planner.planTask('测试任务', mockTools);
            
            expect(plan.goal).toBe('测试任务');});

        it('应该从混合文本中提取 JSON', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '这是执行计划：\n{"goal": "测试任务", "steps": []}\n以上就是计划。',
            });

            const plan = await planner.planTask('测试任务', mockTools);
            
            expect(plan.goal).toBe('测试任务');
        });

        it('应该处理格式错误的 JSON 并返回默认计划', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '这不是有效的 JSON 格式',
            });

            const plan = await planner.planTask('测试任务', mockTools);
            
            // 应该返回默认单步计划
            expect(plan.goal).toBe('测试任务');
            expect(plan.steps).toHaveLength(1);
            expect(plan.steps[0].description).toBe('测试任务');
        });

        it('应该处理带尾随逗号的 JSON', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '{"goal": "测试任务", "steps": [],}',
            });

            const plan = await planner.planTask('测试任务', mockTools);
            
            expect(plan.goal).toBe('测试任务');
        });

        it('应该处理 AI 调用失败的情况', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('AI 调用失败'));

            const plan = await planner.planTask('测试任务', mockTools);
            
            // 应该返回默认单步计划
            expect(plan.goal).toBe('测试任务');
            expect(plan.steps).toHaveLength(1);
        });
    });

    describe('执行计划生成', () => {
        it('应该生成正确格式的 ExecutionPlan', async () => {
            const goalText = '打开Chrome并搜索天气';
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({
                    goal: goalText,
                    steps: [
                        {
                            id: 1,
                            description: '打开 Chrome 浏览器',
                            action: 'apps_open_app',
                            params: { name: 'Chrome' },requiresVision: false,
                dependsOn: [],
                        },
                    ],
                }),
            });

            const plan = await planner.planTask(goalText, mockTools);
            
            expect(plan.goal).toBe(goalText);
            expect(plan.steps).toHaveLength(1);
        });

        it('步骤应该包含正确字段', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({
                    goal: '测试任务',
                    steps: [
                        {
                            id: 1,
                            description: '第一步',
                            action: 'audio_set_volume',
                            params: { volume: 50 },
                            requiresVision: false,
                            dependsOn: [],
                        },
                        {
                            id: 2,
                            description: '第二步',
                            action: 'apps_open_app',
                            params: { name: 'Chrome' },
                            requiresVision: true,
                            dependsOn: [1],
                        },
                    ],
                }),
            });

            const plan = await planner.planTask('测试任务', mockTools);
            
            const step1 = plan.steps[0];
            expect(step1.id).toBe(1);
            expect(step1.description).toBe('第一步');
            expect(step1.action).toBe('audio_set_volume');
            expect(step1.params).toEqual({ volume: 50 });
            expect(step1.requiresVision).toBe(false);
            expect(step1.dependsOn).toEqual([]);

            const step2 = plan.steps[1];
            expect(step2.id).toBe(2);
            expect(step2.requiresVision).toBe(true);
            expect(step2.dependsOn).toEqual([1]);
        });

        it('应该规范化缺失字段的步骤', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({
                    goal: '测试任务',
                    steps: [
                        {
                            description: '只有描述',
                        },
                    ],
                }),
            });

            const plan = await planner.planTask('测试任务', mockTools);
            
            const step = plan.steps[0];
            expect(step.id).toBe(1);
            expect(step.description).toBe('只有描述');
            expect(step.action).toBe('unknown');
            expect(step.params).toEqual({});
            expect(step.requiresVision).toBe(false);
            expect(step.dependsOn).toEqual([]);
        });

        it('应该处理空工具列表', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({
                    goal: '测试任务',
                    steps: [],
                }),
            });

            const plan = await planner.planTask('测试任务', []);
            
            expect(plan).toBeDefined();
        });
    });

    describe('失败处理决策', () => {
        const mockStep: ExecutionStep = {
            id: 1,
            description: '测试步骤',
            action: 'test_action',
            params: {},
            requiresVision: false,
            dependsOn: [],
        };

        it('应该返回 retry 决策', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '{"decision": "retry", "reason": "可以重试"}',
            });

            const decision = await planner.handleFailure(mockStep, new Error('暂时失败'));
            
            expect(decision).toBe('retry');
        });

        it('应该返回 alternative 决策', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '{"decision": "alternative", "reason": "尝试替代方案"}',
            });

            const decision = await planner.handleFailure(mockStep, new Error('主方案失败'));
            
            expect(decision).toBe('alternative');
        });

        it('应该返回 skip 决策', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '{"decision": "skip", "reason": "跳过此步骤"}',
            });

            const decision = await planner.handleFailure(mockStep, new Error('非关键失败'));
            
            expect(decision).toBe('skip');
        });

        it('应该返回 abort 决策', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '{"decision": "abort", "reason": "无法继续"}',
            });

            const decision = await planner.handleFailure(mockStep, new Error('致命错误'));
            
            expect(decision).toBe('abort');
        });

        it('无效决策时应该默认返回 abort', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '{"decision": "invalid", "reason": "无效决策"}',
            });

            const decision = await planner.handleFailure(mockStep, new Error('错误'));
            
            expect(decision).toBe('abort');
        });

        it('解析失败时应该返回 abort', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '这不是有效的 JSON',
            });

            const decision = await planner.handleFailure(mockStep, new Error('错误'));
            
            expect(decision).toBe('abort');
        });

        it('AI 调用失败时应该返回 abort', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('AI 调用失败'));

            const decision = await planner.handleFailure(mockStep, new Error('错误'));
            
            expect(decision).toBe('abort');
        });

        it('应该处理没有错误信息的情况', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '{"decision": "retry", "reason": "重试"}',
            });

            const decision = await planner.handleFailure(mockStep);
            
            expect(decision).toBe('retry');
        });
    });

    describe('结果汇总', () => {
        it('应该汇总成功的结果', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '所有步骤都已成功完成。',
            });

            const results: StepResult[] = [
                { stepId: 1, success: true, output: 'result1' },
                { stepId: 2, success: true, output: 'result2' },
            ];

            const summary = await planner.summarize('测试任务', results);
            
            expect(summary).toBe('所有步骤都已成功完成。');
        });

        it('应该汇总部分失败的结果', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '1 个步骤成功，1 个步骤失败。',
            });

            const results: StepResult[] = [
                { stepId: 1, success: true, output: 'result1' },
                { stepId: 2, success: false, error: new Error('失败') },
            ];

            const summary = await planner.summarize('测试任务', results);
            
            expect(summary).toContain('1');});

        it('AI 调用失败时应该返回降级摘要', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('AI 调用失败'));

            const results: StepResult[] = [
                { stepId: 1, success: true, output: 'result1' },
                { stepId: 2, success: true, output: 'result2' },
            ];

            const summary = await planner.summarize('测试任务', results);
            
            expect(summary).toContain('任务完成');expect(summary).toContain('2');
        });

        it('全部失败时应该返回正确的降级摘要', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('AI 调用失败'));

            const results: StepResult[] = [
                { stepId: 1, success: false, error: new Error('失败1') },
                { stepId: 2, success: false, error: new Error('失败2') },
            ];

            const summary = await planner.summarize('测试任务', results);
            
            // 验证降级摘要包含"部分完成"和失败数字
            expect(summary).toContain('部分完成');
            expect(summary).toContain('0');
            expect(summary).toContain('2');
        });

        it('应该处理空结果列表', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '没有执行任何步骤。',
            });

            const summary = await planner.summarize('测试任务', []);
            
            expect(summary).toBeDefined();
        });
    });

    describe('工具格式化', () => {
        it('应该正确格式化工具列表', async () => {
            const tools: InternalToolDefinition[] = [
                { name: 'tool1', description: '工具1', parameters: {} },
                { name: 'tool2', description: '工具2', parameters: {} },
            ];

            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({ goal: '测试', steps: [] }),
            });

            await planner.planTask('测试', tools);
            
            // 验证 chat 被调用
            expect(mockEngine.chat).toHaveBeenCalled();
        });

        it('应该处理空工具列表', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({ goal: '测试', steps: [] }),
            });

            await planner.planTask('测试', []);
            
            expect(mockEngine.chat).toHaveBeenCalled();
        });

        it('应该限制工具数量', async () => {
            // 创建大量工具
            const manyTools: InternalToolDefinition[] = Array.from({ length: 50 }, (_, i) => ({
                name: `tool${i}`,
                description: `工具${i}`,
                parameters: {},
            }));

            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({ goal: '测试', steps: [] }),
            });

            await planner.planTask('测试', manyTools);
            
            // 验证调用成功
            expect(mockEngine.chat).toHaveBeenCalled();
        });
    });

    describe('边界情况', () => {
        it('应该处理空输入', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({ goal: '默认任务', steps: [] }),
            });

            const plan = await planner.planTask('', mockTools);
            
            expect(plan).toBeDefined();
        });

        it('应该处理非常长的输入', async () => {
            const longInput = '测试'.repeat(1000);
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({ goal: longInput, steps: [] }),
            });

            const plan = await planner.planTask(longInput, mockTools);
            
            expect(plan).toBeDefined();
        });

        it('应该处理特殊字符', async () => {
            (mockEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({ goal: '测试 <script>alert(1)</script>', steps: [] }),
            });

            const plan = await planner.planTask('测试 <script>alert(1)</script>', mockTools);
            
            expect(plan).toBeDefined();
        });
    });
});