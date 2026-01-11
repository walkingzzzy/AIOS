/**
 * 任务编排器
 * 三层 AI 协调的核心：意图分析 → 任务路由 → 执行 → 汇总
 */

import type { IAIEngine, Message, ToolDefinition } from '@aios/shared';
import { toOpenAIToolDefinition } from '@aios/shared';
import type { AdapterRegistry } from './AdapterRegistry.js';
import { IntentAnalyzer } from './IntentAnalyzer.js';
import { ToolExecutor, type ToolExecutionResult } from './ToolExecutor.js';
import { TaskPlanner } from './TaskPlanner.js';
import { ContextManager } from './ContextManager.js';
import { IntentCache } from './IntentCache.js';
import {
    TaskType,
    type TaskContext,
    type TaskResult,
    type TaskAnalysis,
    type StepResult,
    type ExecutionStep,
} from '../types/orchestrator.js';

export interface OrchestratorConfig {
    fastEngine: IAIEngine;
    visionEngine: IAIEngine;
    smartEngine: IAIEngine;
    adapterRegistry: AdapterRegistry;
}

/**
 * 任务编排器 - 三层 AI 协调的核心
 */
export class TaskOrchestrator {
    private intentAnalyzer: IntentAnalyzer;
    private toolExecutor: ToolExecutor;
    private taskPlanner: TaskPlanner;
    private contextManager: ContextManager;
    private intentCache: IntentCache;

    private fastEngine: IAIEngine;
    private visionEngine: IAIEngine;
    private smartEngine: IAIEngine;

    constructor(config: OrchestratorConfig) {
        this.fastEngine = config.fastEngine;
        this.visionEngine = config.visionEngine;
        this.smartEngine = config.smartEngine;

        this.intentAnalyzer = new IntentAnalyzer(config.adapterRegistry);
        this.toolExecutor = new ToolExecutor(config.adapterRegistry);
        this.taskPlanner = new TaskPlanner(config.smartEngine);
        this.contextManager = new ContextManager(10);
        this.intentCache = new IntentCache(100);
    }

    /**
     * 处理用户请求 - 主入口
     */
    async process(input: string, context: TaskContext = {}): Promise<TaskResult> {
        const startTime = Date.now();

        console.log(`[TaskOrchestrator] Processing: "${input.substring(0, 50)}..."`);

        // 1. 分析任务类型
        const analysis = await this.analyzeWithCache(input, context);
        console.log(`[TaskOrchestrator] Task type: ${analysis.taskType}, confidence: ${analysis.confidence}`);

        // 2. 根据类型执行
        let result: TaskResult;
        switch (analysis.taskType) {
            case TaskType.Simple:
                result = await this.executeSimple(input, analysis);
                break;
            case TaskType.Visual:
                result = await this.executeVisual(input, analysis);
                break;
            case TaskType.Complex:
                result = await this.executeComplex(input, analysis);
                break;
            default:
                result = await this.executeSimple(input, analysis);
        }

        // 3. 保存到对话历史
        this.contextManager.addMessage({ role: 'user', content: input });
        this.contextManager.addMessage({ role: 'assistant', content: result.response });

        result.executionTime = Date.now() - startTime;
        console.log(`[TaskOrchestrator] Completed in ${result.executionTime}ms, tier: ${result.tier}`);

        return result;
    }

    /**
     * 带缓存的意图分析
     */
    private async analyzeWithCache(input: string, context: TaskContext): Promise<TaskAnalysis> {
        // 检查缓存
        const cached = this.intentCache.getClassification(input);
        if (cached) {
            return cached;
        }

        // 执行分析
        const analysis = await this.intentAnalyzer.analyze(input, context);
        this.intentCache.setClassification(input, analysis);

        return analysis;
    }

    /**
     * 简单任务执行
     * 路径: 直达匹配 或 Fast 层 AI
     */
    private async executeSimple(input: string, analysis: TaskAnalysis): Promise<TaskResult> {
        // 1. 如果有直达匹配，直接执行
        if (analysis.directToolCall) {
            console.log(`[TaskOrchestrator] Direct tool call: ${analysis.directToolCall.tool}.${analysis.directToolCall.action}`);
            try {
                const result = await this.toolExecutor.execute(analysis.directToolCall);
                return {
                    success: result.success,
                    response: result.message || (result.success ? '操作完成' : '操作失败'),
                    tier: 'direct',
                    executionTime: 0,
                };
            } catch (error) {
                console.error('[TaskOrchestrator] Direct execution failed:', error);
                // 降级到 Fast 层
            }
        }

        // 2. Fast 层 AI 处理
        return this.executeFastLayer(input);
    }

    /**
     * Fast 层执行
     */
    private async executeFastLayer(input: string): Promise<TaskResult> {
        try {
            // 获取对话历史
            const history = this.contextManager.getMessagesForAI(5);
            const messages: Message[] = [
                ...history,
                { role: 'user', content: input },
            ];

            // 获取可用工具并转换为 OpenAI 格式
            const internalTools = this.toolExecutor.getAvailableTools();
            const tools: ToolDefinition[] = internalTools.slice(0, 20).map(t => toOpenAIToolDefinition(t));

            // 调用 Fast 层 AI（带工具）
            const response = await this.fastEngine.chatWithTools(messages, tools);

            // 如果有工具调用
            if (response.toolCalls && response.toolCalls.length > 0) {
                const toolCall = response.toolCalls[0];
                const [tool, action] = toolCall.function.name.split('.');

                console.log(`[TaskOrchestrator] Fast layer tool call: ${toolCall.function.name}`);

                // 解析参数
                const params = JSON.parse(toolCall.function.arguments || '{}');

                const toolResult = await this.toolExecutor.execute({
                    tool,
                    action,
                    params,
                });

                return {
                    success: toolResult.success,
                    response: toolResult.message || response.content || '操作完成',
                    tier: 'fast',
                    executionTime: 0,
                    model: this.fastEngine.name,
                };
            }

            return {
                success: true,
                response: response.content,
                tier: 'fast',
                executionTime: 0,
                model: this.fastEngine.name,
            };
        } catch (error) {
            console.error('[TaskOrchestrator] Fast layer failed:', error);
            return {
                success: false,
                response: `处理失败: ${error instanceof Error ? error.message : '未知错误'}`,
                tier: 'fast',
                executionTime: 0,
            };
        }
    }

    /**
     * 视觉任务执行
     * 路径: Vision 层分析 → Fast 层执行
     */
    private async executeVisual(input: string, analysis: TaskAnalysis): Promise<TaskResult> {
        try {
            console.log('[TaskOrchestrator] Executing visual task...');

            // 1. Vision 层分析屏幕
            const visionPrompt = analysis.visionPrompt || `分析屏幕并执行: ${input}`;

            const visionResponse = await this.visionEngine.chat([
                { role: 'user', content: visionPrompt },
            ]);

            // 2. 检查是否需要执行操作
            const actionMatch = visionResponse.content.match(/\[ACTION\]\s*(\{[\s\S]*?\})/);
            if (actionMatch) {
                try {
                    const action = JSON.parse(actionMatch[1]);
                    const actionResult = await this.toolExecutor.executeAction(action);
                    return {
                        success: actionResult.success,
                        response: actionResult.message || '视觉操作完成',
                        tier: 'vision',
                        executionTime: 0,
                        model: this.visionEngine.name,
                    };
                } catch {
                    // 操作解析失败，返回分析结果
                }
            }

            // 3. 返回视觉分析结果
            return {
                success: true,
                response: visionResponse.content,
                tier: 'vision',
                executionTime: 0,
                model: this.visionEngine.name,
            };
        } catch (error) {
            console.error('[TaskOrchestrator] Vision layer failed:', error);
            return {
                success: false,
                response: `视觉分析失败: ${error instanceof Error ? error.message : '未知错误'}`,
                tier: 'vision',
                executionTime: 0,
            };
        }
    }

    /**
     * 复杂任务执行
     * 路径: Smart 层规划 → 循环执行 → Smart 层汇总
     */
    private async executeComplex(input: string, _analysis: TaskAnalysis): Promise<TaskResult> {
        try {
            console.log('[TaskOrchestrator] Executing complex task...');

            // 1. Smart 层生成执行计划
            const tools = this.toolExecutor.getAvailableTools();
            const plan = await this.taskPlanner.planTask(input, tools);
            console.log(`[TaskOrchestrator] Plan generated: ${plan.steps.length} steps`);

            // 2. 按步骤执行
            const stepResults: StepResult[] = [];
            for (const step of plan.steps) {
                console.log(`[TaskOrchestrator] Executing step ${step.id}: ${step.description}`);

                const result = await this.executeStep(step);
                stepResults.push(result);

                // 失败处理
                if (!result.success) {
                    const decision = await this.taskPlanner.handleFailure(step, result.error);
                    console.log(`[TaskOrchestrator] Step failed, decision: ${decision}`);

                    if (decision === 'abort') {
                        break;
                    }
                }
            }

            // 3. Smart 层汇总结果
            const summary = await this.taskPlanner.summarize(input, stepResults);

            return {
                success: stepResults.every(r => r.success),
                response: summary,
                tier: 'smart',
                executionTime: 0,
                model: this.smartEngine.name,
            };
        } catch (error) {
            console.error('[TaskOrchestrator] Complex task failed:', error);
            return {
                success: false,
                response: `任务执行失败: ${error instanceof Error ? error.message : '未知错误'}`,
                tier: 'smart',
                executionTime: 0,
            };
        }
    }

    /**
     * 执行单个步骤
     */
    private async executeStep(step: ExecutionStep): Promise<StepResult> {
        try {
            // 视觉步骤
            if (step.requiresVision) {
                const visionResult = await this.visionEngine.chat([
                    { role: 'user', content: step.description },
                ]);
                return {
                    stepId: step.id,
                    success: true,
                    output: visionResult.content,
                };
            }

            // 工具步骤
            const [tool, action] = step.action.split('.');
            if (!tool || !action) {
                return {
                    stepId: step.id,
                    success: false,
                    error: new Error(`无效的动作格式: ${step.action}`),
                };
            }

            const result = await this.toolExecutor.execute({
                tool,
                action,
                params: step.params,
            });

            return {
                stepId: step.id,
                success: result.success,
                output: result.data,
                error: result.success ? undefined : new Error(result.message),
            };
        } catch (error) {
            return {
                stepId: step.id,
                success: false,
                error: error instanceof Error ? error : new Error(String(error)),
            };
        }
    }
}
