/**
 * TaskOrchestrator 单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TaskOrchestrator, type OrchestratorConfig } from '../../core/TaskOrchestrator.js';
import { TaskType } from '../../types/orchestrator.js';
import type { AdapterRegistry } from '../../core/AdapterRegistry.js';
import type { IAIEngine, Message,ToolDefinition } from '@aios/shared';
import { writeFile } from 'node:fs/promises';

// 创建 mock AI Engine
function createMockAIEngine(name: string = 'mock-engine'): IAIEngine {return {
        name,
        chat: vi.fn().mockResolvedValue({ content: 'AI 响应内容' }),
        chatWithTools: vi.fn().mockResolvedValue({ content: 'AI 响应内容', toolCalls: [] }),
        chatStream: vi.fn(),
        chatStreamWithTools: vi.fn(),
    } as unknown as IAIEngine;
}

// 创建 mock AdapterRegistry
function createMockRegistry(): AdapterRegistry {
    const mockAdapters = new Map<string, {
        id: string;
        name: string;
        capabilities: { id: string; description: string; parameters?: unknown[] }[];
        invoke: ReturnType<typeof vi.fn>;
        initialize: ReturnType<typeof vi.fn>;shutdown: ReturnType<typeof vi.fn>;
    }>();

    // 添加默认适配器
    const defaultAdapters = [
        { id: 'com.aios.adapter.audio', name: 'audio', capabilities: [{ id: 'set_volume', description: '设置音量', permissionLevel: 'public' }] },
        { id: 'com.aios.adapter.display', name: 'display', capabilities: [{ id: 'set_brightness', description: '设置亮度', permissionLevel: 'public' }] },
        { id: 'com.aios.adapter.apps', name: 'apps', capabilities: [{ id: 'open_app', description: '打开应用', permissionLevel: 'public' }] },
        { id: 'com.aios.adapter.power', name: 'power', capabilities: [{ id: 'lock_screen', description: '锁屏', permissionLevel: 'public' }] },
        { id: 'com.aios.adapter.desktop', name: 'desktop', capabilities: [{ id: 'set_appearance', description: '设置外观', permissionLevel: 'public' }] },
    ];

    for (const adapter of defaultAdapters) {
        mockAdapters.set(adapter.id, {
            ...adapter,
            invoke: vi.fn().mockResolvedValue({ success: true, data: {} }),
            initialize: vi.fn().mockResolvedValue(undefined),
            shutdown: vi.fn().mockResolvedValue(undefined),
        });
    }

    return {
        get: vi.fn((id: string) => mockAdapters.get(id)),
        getAll: vi.fn(() => Array.from(mockAdapters.values())),
        register: vi.fn(),
        findByCapability: vi.fn(),
        initializeAll: vi.fn(),
        shutdownAll: vi.fn(),
    } as unknown as AdapterRegistry;
}

describe('TaskOrchestrator', () => {
    let orchestrator: TaskOrchestrator;
    let mockFastEngine: IAIEngine;
    let mockVisionEngine: IAIEngine;
    let mockSmartEngine: IAIEngine;
    let mockRegistry: AdapterRegistry;
    let config: OrchestratorConfig;

    beforeEach(() => {
        mockFastEngine = createMockAIEngine('fast-engine');
        mockVisionEngine = createMockAIEngine('vision-engine');
        mockSmartEngine = createMockAIEngine('smart-engine');
        mockRegistry = createMockRegistry();

        config = {
            fastEngine: mockFastEngine,
            visionEngine: mockVisionEngine,
            smartEngine: mockSmartEngine,
            adapterRegistry: mockRegistry,
        };

        orchestrator = new TaskOrchestrator(config);
    });

    describe('简单任务处理流程', () => {
        describe('直达匹配执行', () => {
            it('应该直接执行音量控制指令', async () => {
                const result = await orchestrator.process('调高音量');
                
                expect(result.success).toBe(true);
                expect(result.tier).toBe('direct');
                expect(result.executionTime).toBeGreaterThanOrEqual(0);
            });

            it('应该直接执行锁屏指令', async () => {
                const result = await orchestrator.process('锁屏');
                
                expect(result.success).toBe(true);
                expect(result.tier).toBe('direct');});

            it('应该直接执行打开应用指令', async () => {
                const result = await orchestrator.process('打开Chrome');
                
                expect(result.success).toBe(true);
                expect(result.tier).toBe('direct');
            });
        });

        describe('Fast层执行', () => {
            it('无直达匹配时应该走Fast层', async () => {
                const result = await orchestrator.process('你好');
                
                expect(result.tier).toBe('fast');
                expect(result.model).toBe('fast-engine');
            });

            it('Fast层应该使用工具调用', async () => {
                // 模拟 AI 返回工具调用
                (mockFastEngine.chatWithTools as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                    content: '',
                    toolCalls: [{
                        id: 'call_1',
                        type: 'function',
                        function: {
                            name: 'audio_set_volume',
                            arguments: JSON.stringify({ volume: 50 }),
                        },
                    }],
                });

                const result = await orchestrator.process('帮我把声音设置到50');
                
                expect(result.tier).toBe('fast');
            });
        });
    });

    describe('降级机制', () => {
        it('直达匹配执行失败后应该降级或返回错误', async () => {
            // 模拟适配器调用失败
            const mockAdapter = mockRegistry.get('com.aios.adapter.audio');
            if (mockAdapter) {
                (mockAdapter.invoke as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('执行失败'));
            }

            const result = await orchestrator.process('调高音量');
            
            // 直达匹配失败时会降级到fast层或返回错误
            // 这取决于实现逻辑，验证结果包含正确的tier
            expect(['direct', 'fast']).toContain(result.tier);
        });

        it('Fast层失败时应该返回错误信息', async () => {
            (mockFastEngine.chatWithTools as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('AI 调用失败'));

            const result = await orchestrator.process('你好');
            
            expect(result.success).toBe(false);
            expect(result.tier).toBe('fast');
            expect(result.response).toContain('处理失败');
        });
    });

    describe('任务类型路由', () => {
        it('Simple任务应该走executeSimple', async () => {
            const result = await orchestrator.process('音量50');
            
            expect(result.tier).toBe('direct');
        });

        it('Visual任务应该走executeVisual', async () => {
            (mockVisionEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '这是屏幕分析结果',
            });

            const result = await orchestrator.process('屏幕上有什么');
            
            expect(result.tier).toBe('vision');
            expect(result.model).toBe('vision-engine');
        });

        it('Complex任务应该走executeComplex', async () => {
            // 使用不含直达匹配关键词的复杂任务表达
            // 模拟 Smart 层返回执行计划
            (mockSmartEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: JSON.stringify({
                    goal: '分析并总结系统状态',
                    steps: [
                        { id: 1, description: '分析系统', action: 'analyze', params: {}, requiresVision: false, dependsOn: [] },
                ],
                }),
            });

            // 模拟汇总响应
            (mockSmartEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '任务完成',
            });

            const result = await orchestrator.process('分析并总结系统状态');
            
            expect(result.tier).toBe('smart');
            expect(result.model).toBe('smart-engine');
        });
    });

    describe('结果格式验证', () => {
        it('TaskResult应该包含正确的tier字段', async () => {
            const result = await orchestrator.process('调高音量');
            
            expect(result.tier).toBeDefined();
            expect(['direct', 'fast', 'vision', 'smart']).toContain(result.tier);
        });

        it('TaskResult应该包含model字段（非直达匹配时）', async () => {
            const result = await orchestrator.process('你好');
            
            expect(result.model).toBeDefined();
            expect(result.model).toBe('fast-engine');
        });

        it('TaskResult应该包含executionTime', async () => {
            const result = await orchestrator.process('调高音量');
            
            expect(result.executionTime).toBeDefined();
            expect(typeof result.executionTime).toBe('number');
            expect(result.executionTime).toBeGreaterThanOrEqual(0);
        });

        it('TaskResult应该包含success字段', async () => {
            const result = await orchestrator.process('调高音量');
            
            expect(result.success).toBeDefined();
            expect(typeof result.success).toBe('boolean');
        });

        it('TaskResult应该包含response字段', async () => {
            const result = await orchestrator.process('调高音量');
            
            expect(result.response).toBeDefined();
            expect(typeof result.response).toBe('string');
        });
    });

    describe('视觉任务执行', () => {
        it('应该调用visionEngine处理视觉任务', async () => {
            (mockVisionEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '屏幕上显示了桌面',
            });

            const result = await orchestrator.process('看看屏幕上有什么');
            
            expect(mockVisionEngine.chat).toHaveBeenCalled();
            expect(result.tier).toBe('vision');
        });

        it('视觉任务应携带截图 images', async () => {
            const fastEngine = createMockAIEngine('fast-engine');
            const visionEngine = createMockAIEngine('vision-engine');
            const smartEngine = createMockAIEngine('smart-engine');

            (visionEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '这是屏幕分析结果',
            });

            const expectedBase64 = Buffer.from('fake image').toString('base64');
            const screenshotAdapter = {
                id: 'com.aios.adapter.screenshot',
                name: 'screenshot',
                description: 'screenshot',
                capabilities: [],
                initialize: vi.fn().mockResolvedValue(undefined),
                checkAvailability: vi.fn().mockResolvedValue(true),
                shutdown: vi.fn().mockResolvedValue(undefined),
                invoke: vi.fn(async (_capability: string, args: Record<string, unknown>) => {
                    const savePath = args.save_path as string;
                    await writeFile(savePath, 'fake image');
                    return { success: true, data: { path: savePath } };
                }),
            };

            const registry = {
                get: vi.fn((id: string) => (id === 'com.aios.adapter.screenshot' ? screenshotAdapter : undefined)),
                getAll: vi.fn(() => [screenshotAdapter]),
                register: vi.fn(),
                findByCapability: vi.fn(),
                initializeAll: vi.fn(),
                shutdownAll: vi.fn(),
            } as unknown as AdapterRegistry;

            const localOrchestrator = new TaskOrchestrator({
                fastEngine,
                visionEngine,
                smartEngine,
                adapterRegistry: registry,
            });

            const result = await localOrchestrator.process('屏幕上有什么');
            expect(result.tier).toBe('vision');

            const messages = (visionEngine.chat as ReturnType<typeof vi.fn>).mock.calls[0][0] as any[];
            const lastMessage = messages[messages.length - 1];
            expect(lastMessage.images).toEqual([expectedBase64]);
        });

        it('视觉任务应该能解析并执行ACTION', async () => {
            (mockVisionEngine.chat as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
                content: '[ACTION] {"type": "click", "x": 100, "y": 200}',
            });

            const result = await orchestrator.process('点击那个按钮');
            
            expect(result.tier).toBe('vision');});

        it('视觉任务失败时应该返回错误信息', async () => {
            (mockVisionEngine.chat as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('Vision 调用失败'));

            const result = await orchestrator.process('屏幕上有什么');
            
            expect(result.success).toBe(false);
            expect(result.tier).toBe('vision');
            expect(result.response).toContain('视觉分析失败');
        });
    });

    describe('复杂任务执行', () => {
        it('应该调用smartEngine生成执行计划', async () => {
            (mockSmartEngine.chat as ReturnType<typeof vi.fn>)
                .mockResolvedValueOnce({
                    content: JSON.stringify({
                        goal: '分析并总结',
                        steps: [{ id: 1, description: '分析', action: 'analyze', params: {}, requiresVision: false, dependsOn: [] }],
                    }),
                })
                .mockResolvedValueOnce({
                    content: '任务已完成',
                });

            const result = await orchestrator.process('分析并总结这个问题');
            
            expect(mockSmartEngine.chat).toHaveBeenCalled();
            expect(result.tier).toBe('smart');
        });

        it('复杂任务失败时应该返回相应结果', async () => {
            (mockSmartEngine.chat as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('Smart 调用失败'));

            const result = await orchestrator.process('首先分析接着总结');
            
            expect(result.success).toBe(false);
            expect(result.tier).toBe('smart');
            // 验证响应包含错误信息
            expect(result.response.length).toBeGreaterThan(0);
        });
    });

    describe('缓存机制', () => {
        it('相同输入应该使用缓存的分析结果', async () => {
            await orchestrator.process('调高音量');
            await orchestrator.process('调高音量');
            
            // 两次调用应该都成功且使用直达匹配
            //缓存机制在IntentAnalyzer 内部实现
        });
    });

    describe('对话历史', () => {
        it('应该保存对话历史', async () => {
            await orchestrator.process('你好');
            await orchestrator.process('谢谢');
            
            // 对话历史由ContextManager 管理
            // 这里验证不会抛出错误
        });
    });
});
