/**
 * IntentAnalyzer 单元测试
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { IntentAnalyzer } from '../../core/IntentAnalyzer.js';
import { TaskType } from '../../types/orchestrator.js';
import type { AdapterRegistry } from '../../core/AdapterRegistry.js';

//创建 mock AdapterRegistry
function createMockRegistry(adapters: string[] = []): AdapterRegistry {
    const mockAdapters = new Map<string, { id: string; name: string; capabilities: { id: string }[] }>();
    
    // 添加默认适配器
    const defaultAdapters = [
        'com.aios.adapter.audio',
        'com.aios.adapter.display',
        'com.aios.adapter.apps',
        'com.aios.adapter.power',
        'com.aios.adapter.desktop',
        'com.aios.adapter.speech',
        'com.aios.adapter.notification',
        'com.aios.adapter.calculator',
        'com.aios.adapter.systeminfo',
        'com.aios.adapter.weather',
        'com.aios.adapter.translate',
        ...adapters,
    ];
    
    for (const adapterId of defaultAdapters) {
        mockAdapters.set(adapterId, {
            id: adapterId,
            name: adapterId.split('.').pop() || '',
            capabilities: [],
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

describe('IntentAnalyzer', () => {
    let analyzer: IntentAnalyzer;
    let mockRegistry: AdapterRegistry;

    beforeEach(() => {
        mockRegistry = createMockRegistry();
        analyzer = new IntentAnalyzer(mockRegistry);
    });

    describe('直达匹配测试', () => {
        describe('音量控制', () => {
            it('应该匹配"调高音量"指令', async () => {
                const result = await analyzer.analyze('调高音量');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.audio');
                expect(result.directToolCall?.action).toBe('set_volume');
                expect(result.directToolCall?.params).toEqual({ volume: 80 });
            });

            it('应该匹配"调低音量"指令', async () => {
                const result = await analyzer.analyze('调低音量');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.audio');
                expect(result.directToolCall?.action).toBe('set_volume');
                expect(result.directToolCall?.params).toEqual({ volume: 30 });
            });

            it('应该匹配"音量50"指令并提取参数', async () => {
                const result = await analyzer.analyze('音量50');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.audio');
                expect(result.directToolCall?.action).toBe('set_volume');
                expect(result.directToolCall?.params).toEqual({ volume: 50 });
            });

            it('应该匹配"静音"指令', async () => {
                const result = await analyzer.analyze('静音');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.audio');
                expect(result.directToolCall?.action).toBe('set_muted');
                expect(result.directToolCall?.params).toEqual({ muted: true });
            });

            it('应该匹配"取消静音"指令', async () => {
                const result = await analyzer.analyze('取消静音');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.audio');
                expect(result.directToolCall?.action).toBe('set_muted');
                expect(result.directToolCall?.params).toEqual({ muted: false });
            });

            it('应该匹配"取消 静音"指令', async () => {
                const result = await analyzer.analyze('取消 静音');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.audio');
                expect(result.directToolCall?.action).toBe('set_muted');
                expect(result.directToolCall?.params).toEqual({ muted: false });
            });
        });

        describe('亮度控制', () => {
            it('应该匹配"调高亮度"指令', async () => {
                const result = await analyzer.analyze('调高亮度');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.display');
                expect(result.directToolCall?.action).toBe('set_brightness');
                expect(result.directToolCall?.params).toEqual({ brightness: 80 });
            });

            it('应该匹配"调低亮度"指令', async () => {
                const result = await analyzer.analyze('调低亮度');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.display');
                expect(result.directToolCall?.action).toBe('set_brightness');
                expect(result.directToolCall?.params).toEqual({ brightness: 30 });
            });

            it('应该匹配"亮度80"指令并提取参数', async () => {
                const result = await analyzer.analyze('亮度80');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.display');
                expect(result.directToolCall?.action).toBe('set_brightness');
                expect(result.directToolCall?.params).toEqual({ brightness: 80 });
            });
        });

        describe('应用控制', () => {
            it('应该匹配"打开Chrome"指令', async () => {
                const result = await analyzer.analyze('打开Chrome');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.apps');
                expect(result.directToolCall?.action).toBe('open_app');
                expect(result.directToolCall?.params).toEqual({ name: 'Chrome' });
            });

            it('应该匹配"关闭微信"指令', async () => {
                const result = await analyzer.analyze('关闭微信');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.apps');
                expect(result.directToolCall?.action).toBe('close_app');
                expect(result.directToolCall?.params).toEqual({ name: '微信' });
            });

            it('应该匹配"启动Safari"指令', async () => {
                const result = await analyzer.analyze('启动Safari');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.apps');
                expect(result.directToolCall?.action).toBe('open_app');
                expect(result.directToolCall?.params).toEqual({ name: 'Safari' });
            });
        });

        describe('电源控制', () => {
            it('应该匹配"锁屏"指令', async () => {
                const result = await analyzer.analyze('锁屏');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.power');
                expect(result.directToolCall?.action).toBe('lock_screen');
            });

            it('应该匹配"休眠"指令', async () => {
                const result = await analyzer.analyze('休眠');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.power');
                expect(result.directToolCall?.action).toBe('sleep');
            });

            it('应该匹配"关机"指令', async () => {
                const result = await analyzer.analyze('关机');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.power');
                expect(result.directToolCall?.action).toBe('shutdown');
                expect(result.directToolCall?.params).toEqual({ confirm: true, delay: 60 });
            });

            it('应该匹配"重启"指令', async () => {
                const result = await analyzer.analyze('重启');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.power');
                expect(result.directToolCall?.action).toBe('restart');
                expect(result.directToolCall?.params).toEqual({ confirm: true, delay: 60 });
            });
        });

        describe('其他直达匹配', () => {
            it('应该匹配"深色模式"指令', async () => {
                const result = await analyzer.analyze('深色模式');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.desktop');
                expect(result.directToolCall?.action).toBe('set_appearance');
                expect(result.directToolCall?.params).toEqual({ mode: 'dark' });
            });

            it('应该匹配"电池"查询指令', async () => {
                const result = await analyzer.analyze('电池');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.systeminfo');
                expect(result.directToolCall?.action).toBe('get_battery');
            });

            it('应该匹配"北京天气"指令', async () => {
                const result = await analyzer.analyze('北京天气');
                expect(result.directToolCall).toBeDefined();
                expect(result.directToolCall?.tool).toBe('com.aios.adapter.weather');
                expect(result.directToolCall?.action).toBe('get_current_weather');
                expect(result.directToolCall?.params).toEqual({ city: '北京' });
            });
        });
    });

    describe('视觉任务判断', () => {
        it('应该返回 requiresVision=true 对于"屏幕上有什么"', async () => {
            const result = await analyzer.analyze('屏幕上有什么');
            expect(result.taskType).toBe(TaskType.Visual);
        });

        it('应该返回 requiresVision=true 对于"点击按钮"', async () => {
            const result = await analyzer.analyze('点击那个按钮');
            expect(result.taskType).toBe(TaskType.Visual);
        });

        it('应该返回 requiresVision=true 对于"看看当前画面"', async () => {
            const result = await analyzer.analyze('看看当前画面');
            expect(result.taskType).toBe(TaskType.Visual);
        });

        it('应该返回 requiresVision=true 对于"界面显示什么"', async () => {
            const result = await analyzer.analyze('界面显示什么');
            expect(result.taskType).toBe(TaskType.Visual);
        });

        it('应该返回 Simple 类型对于"调高音量"', async () => {
            const result = await analyzer.analyze('调高音量');
            expect(result.taskType).toBe(TaskType.Simple);
        });

        it('应该使用上下文中的截图信息', async () => {
            const result = await analyzer.analyze('这是什么', { hasScreenshot: true });
            expect(result.taskType).toBe(TaskType.Visual);});
    });

    describe('复杂任务判断', () => {
        it('应该返回 isComplex=true 对于多步骤任务', async () => {
            // 注意：原始输入"先打开Chrome然后搜索天气"会被"打开Chrome"直达匹配优先捕获
            // 使用不含直达匹配关键词的复杂任务
            const result = await analyzer.analyze('首先分析系统状态接着生成报告');
            expect(result.taskType).toBe(TaskType.Complex);expect(result.requiresPlanning).toBe(true);
        });

        it('应该返回 isComplex=true 对于"首先分析问题接着给出方案"', async () => {
            const result = await analyzer.analyze('首先分析问题接着给出方案');
            expect(result.taskType).toBe(TaskType.Complex);
            expect(result.requiresPlanning).toBe(true);
        });

        it('应该返回 isComplex=true 对于"分析这段代码"', async () => {
            const result = await analyzer.analyze('分析这段代码');
            expect(result.taskType).toBe(TaskType.Complex);
        });

        it('应该返回 isComplex=true 对于"总结今天的工作"', async () => {
            const result = await analyzer.analyze('总结今天的工作');
            expect(result.taskType).toBe(TaskType.Complex);
        });

        it('应该返回 isComplex=true 对于"比较这两个方案"', async () => {
            const result = await analyzer.analyze('比较这两个方案');
            expect(result.taskType).toBe(TaskType.Complex);
        });

        it('应该返回 isComplex=true 对于"如果成功就继续"', async () => {
            const result = await analyzer.analyze('如果成功就继续');
            expect(result.taskType).toBe(TaskType.Complex);
        });

        it('应该返回 Simple 类型对于"打开Chrome"', async () => {
            const result = await analyzer.analyze('打开Chrome');
            expect(result.taskType).toBe(TaskType.Simple);
        });
    });

    describe('任务类型分类', () => {
        it('Simple 任务应该有 taskType=Simple', async () => {
            const result = await analyzer.analyze('音量50');
            expect(result.taskType).toBe(TaskType.Simple);
        });

        it('Visual 任务应该有 taskType=Visual', async () => {
            const result = await analyzer.analyze('屏幕上显示了什么');
            expect(result.taskType).toBe(TaskType.Visual);expect(result.visionPrompt).toBeDefined();
        });

        it('Complex 任务应该有 taskType=Complex', async () => {
            const result = await analyzer.analyze('分析并总结这个问题');
            expect(result.taskType).toBe(TaskType.Complex);
            expect(result.requiresPlanning).toBe(true);
        });

        it('默认无匹配时应该返回 Simple 类型', async () => {
            const result = await analyzer.analyze('你好');
            expect(result.taskType).toBe(TaskType.Simple);expect(result.directToolCall).toBeUndefined();
        });
    });

    describe('置信度', () => {
        it('直达匹配应该有较高置信度', async () => {
            const result = await analyzer.analyze('调高音量');
            expect(result.confidence).toBeGreaterThanOrEqual(0.9);
        });

        it('视觉任务应该有中等置信度', async () => {
            const result = await analyzer.analyze('屏幕上有什么');
            expect(result.confidence).toBeGreaterThanOrEqual(0.8);
        });

        it('复杂任务应该有中等置信度', async () => {
            const result = await analyzer.analyze('首先分析接着总结');
            expect(result.confidence).toBeGreaterThanOrEqual(0.7);
        });

        it('默认任务应该有较低置信度', async () => {
            const result = await analyzer.analyze('你好');
            expect(result.confidence).toBeLessThanOrEqual(0.7);
        });
    });

    describe('matchDirectTool 方法', () => {
        it('应该返回 null 对于不匹配的输入', () => {
            const result = analyzer.matchDirectTool('你好');
            expect(result).toBeNull();
        });

        it('应该返回正确的 ToolCall 对于匹配的输入', () => {
            const result = analyzer.matchDirectTool('调高音量');
            expect(result).toBeDefined();
            expect(result?.tool).toBe('com.aios.adapter.audio');
            expect(result?.action).toBe('set_volume');
        });

        it('适配器不存在时应该返回 null', () => {
            // 创建一个没有 audio 适配器的registry
            const emptyRegistry = {
                get: vi.fn(() => undefined),
                getAll: vi.fn(() => []),
            } as unknown as AdapterRegistry;
            const analyzerWithEmptyRegistry = new IntentAnalyzer(emptyRegistry);
            
            const result = analyzerWithEmptyRegistry.matchDirectTool('调高音量');
            expect(result).toBeNull();
        });
    });

    describe('visionPrompt 生成', () => {
        it('应该为视觉任务生成 visionPrompt', async () => {
            const result = await analyzer.analyze('看看屏幕上有什么');
            expect(result.visionPrompt).toBeDefined();
            expect(result.visionPrompt).toContain('看看屏幕上有什么');
        });

        it('visionPrompt 应该包含用户请求', async () => {
            const result = await analyzer.analyze('当前画面是什么');
            expect(result.visionPrompt).toContain('当前画面是什么');
        });
    });
});
