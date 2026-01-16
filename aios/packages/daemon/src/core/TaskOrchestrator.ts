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
import { readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
    PromptGuard,
    promptGuard,
    ConfirmationManager,
} from './orchestration/index.js';
import {
    PlanManager,
    ReActOrchestrator,
    type AIEngine,
} from './planning/index.js';
import {
    TaskType,
    type TaskContext,
    type TaskResult,
    type TaskAnalysis,
    type StepResult,
    type ExecutionStep,
} from '../types/orchestrator.js';
import { SkillRegistry } from './skills/SkillRegistry.js';
import { ProjectMemoryManager } from './skills/ProjectMemoryManager.js';
import { WorkerPool, type WorkerExecutor } from './orchestration/WorkerPool.js';
import { TaskDecomposer } from './orchestration/TaskDecomposer.js';
import type { HookManager } from './hooks/index.js';
import { traceContextManager } from './trace/index.js';

export interface OrchestratorConfig {
    fastEngine: IAIEngine;
    visionEngine: IAIEngine;
    smartEngine: IAIEngine;
    adapterRegistry: AdapterRegistry;
    /** 确认管理器（用于高危操作确认） */
    confirmationManager?: ConfirmationManager;
    /** 是否启用高危操作确认 */
    enableConfirmation?: boolean;
    /** 是否启用 ReAct 循环执行复杂任务 */
    enableReAct?: boolean;
    /** 技能注册表 */
    skillRegistry?: SkillRegistry;
    /** 项目记忆管理器 */
    projectMemoryManager?: ProjectMemoryManager;
    /** 是否启用技能系统 */
    enableSkills?: boolean;
    /** 是否启用 O-W 模式 */
    enableOrchestratorWorker?: boolean;
    /** 并行 Worker 数量 */
    maxWorkers?: number;
    /** Hook 管理器（用于审计/用量/追踪/进度） */
    hookManager?: HookManager;
}

interface ExecutionContext {
    taskId: string;
    sessionId?: string;
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
    private adapterRegistry: AdapterRegistry;
    private hookManager?: HookManager;
    private confirmationManager?: ConfirmationManager;
    private enableConfirmation: boolean;
    private reActOrchestrator?: ReActOrchestrator;
    private enableReAct: boolean;
    private skillRegistry?: SkillRegistry;
    private projectMemoryManager?: ProjectMemoryManager;
    private enableSkills: boolean;
    private taskDecomposer?: TaskDecomposer;
    private workerPool?: WorkerPool;
    private enableOW: boolean;

    private fastEngine: IAIEngine;
    private visionEngine: IAIEngine;
    private smartEngine: IAIEngine;

    constructor(config: OrchestratorConfig) {
        this.fastEngine = config.fastEngine;
        this.visionEngine = config.visionEngine;
        this.smartEngine = config.smartEngine;

        this.adapterRegistry = config.adapterRegistry;
        this.hookManager = config.hookManager;
        this.intentAnalyzer = new IntentAnalyzer(config.adapterRegistry);
        this.toolExecutor = new ToolExecutor(config.adapterRegistry);
        this.toolExecutor.setHookManager(this.hookManager);
        this.taskPlanner = new TaskPlanner(config.smartEngine);
        this.contextManager = new ContextManager(10);
        this.intentCache = new IntentCache(100);

        // Phase 8: 确认管理器
        this.confirmationManager = config.confirmationManager;
        this.enableConfirmation = config.enableConfirmation ?? false;

        // Phase 6: ReAct 循环编排器
        this.enableReAct = config.enableReAct ?? false;
        if (this.enableReAct) {
            const planManager = new PlanManager({ enableFilePersistence: false });
            // 将 IAIEngine 适配为 AIEngine 接口
            const aiAdapter: AIEngine = {
                chat: async (messages: unknown[]) => {
                    const response = await config.smartEngine.chat(
                        messages as Message[]
                    );
                    return response.content;
                },
            };
            this.reActOrchestrator = new ReActOrchestrator(aiAdapter, planManager, {
                verbose: true,
                maxIterations: 10,
            });
        }

        // Phase 7: Skills 系统
        this.skillRegistry = config.skillRegistry;
        this.projectMemoryManager = config.projectMemoryManager;
        this.enableSkills = config.enableSkills ?? false;

        // 加载项目记忆
        if (this.projectMemoryManager) {
            this.projectMemoryManager.load();
        }

        // Phase 8: O-W 模式
        this.enableOW = config.enableOrchestratorWorker ?? false;
        if (this.enableOW) {
            this.taskDecomposer = new TaskDecomposer();
            const workerExecutor: WorkerExecutor = async (subTask) => {
                const result = await this.executeFastLayer(subTask.description);
                return result.response;
            };
            this.workerPool = new WorkerPool(workerExecutor, { maxWorkers: config.maxWorkers ?? 5 });
        }
    }

    private async captureScreenshotBase64(): Promise<string | null> {
        const screenshotAdapter = this.adapterRegistry.get('com.aios.adapter.screenshot');
        if (!screenshotAdapter) return null;

        const outputPath = join(tmpdir(), `aios-screenshot-${Date.now()}.png`);

        try {
            const result = await screenshotAdapter.invoke('capture_screen', { save_path: outputPath });
            if (!result.success) return null;

            const path = (result.data as { path?: string } | undefined)?.path || outputPath;
            const buffer = await readFile(path);
            return buffer.toString('base64');
        } catch (error) {
            console.warn('[TaskOrchestrator] Screenshot capture failed:', error);
            return null;
        } finally {
            try {
                await rm(outputPath, { force: true });
            } catch {
                // ignore
            }
        }
    }

    /**
     * 构建系统提示词（包含技能和项目记忆）
     */
    private buildSystemPrompt(): string {
        const parts: string[] = [];

        // 注入项目记忆
        if (this.projectMemoryManager?.isLoaded()) {
            const memoryContext = this.projectMemoryManager.toSystemPromptContext();
            if (memoryContext) {
                parts.push('## Project Context\n' + memoryContext);
            }
        }

        // 注入技能摘要
        if (this.enableSkills && this.skillRegistry) {
            const summaries = this.skillRegistry.getSummaries();
            if (summaries.length > 0) {
                parts.push('## Available Skills\n' +
                    summaries.map(s => `- **${s.name}**: ${s.description}`).join('\n'));
            }
        }

        return parts.join('\n\n');
    }

    /**
     * 根据意图加载匹配的技能
     */
    private loadMatchingSkills(input: string): string {
        if (!this.enableSkills || !this.skillRegistry) return '';

        const matches = this.skillRegistry.match(input, 3);
        const skillContents: string[] = [];

        for (const match of matches) {
            if (match.score > 0.5) {
                const level = match.score > 0.8 ? 'full' : 'instructions';
                const loaded = this.skillRegistry.loadProgressive(match.skill.id, level, 2000);
                if (loaded.content) {
                    skillContents.push(loaded.content);
                }
            }
        }

        return skillContents.join('\n\n');
    }

    /**
     * 处理用户请求 - 主入口
     */
    async process(input: string, context: TaskContext = {}): Promise<TaskResult> {
        const startTime = Date.now();
        const execCtx: ExecutionContext = {
            taskId: context.taskId ?? `task_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
            sessionId: context.sessionId,
        };

        const traceCtx = traceContextManager.create();

        return traceContextManager.runAsync(traceCtx, async () => {
            try {
                console.log(`[TaskOrchestrator] Processing: "${input.substring(0, 50)}..."`);

                // 1. 分析任务类型
                const analysis = await this.analyzeWithCache(input, context);
                console.log(`[TaskOrchestrator] Task type: ${analysis.taskType}, confidence: ${analysis.confidence}`);

                await this.hookManager?.triggerTaskStart({
                    taskId: execCtx.taskId,
                    input,
                    analysis,
                    timestamp: startTime,
                });

                // 2. 根据类型执行
                let result: TaskResult;
                switch (analysis.taskType) {
                    case TaskType.Simple:
                        result = await this.executeSimple(input, analysis, execCtx);
                        break;
                    case TaskType.Visual:
                        result = await this.executeVisual(input, analysis, execCtx);
                        break;
                    case TaskType.Complex:
                        result = await this.executeComplex(input, analysis, execCtx);
                        break;
                    default:
                        result = await this.executeSimple(input, analysis, execCtx);
                }

                // 3. 保存到对话历史
                this.contextManager.addMessage({ role: 'user', content: input });
                this.contextManager.addMessage({ role: 'assistant', content: result.response });

                result.executionTime = Date.now() - startTime;
                console.log(`[TaskOrchestrator] Completed in ${result.executionTime}ms, tier: ${result.tier}`);

                await this.hookManager?.triggerTaskComplete({
                    taskId: execCtx.taskId,
                    result,
                    timestamp: Date.now(),
                    duration: result.executionTime,
                    sessionId: execCtx.sessionId,
                    traceId: traceCtx.traceId,
                });

                return result;
            } catch (error) {
                const err = error instanceof Error ? error : new Error(String(error));
                await this.hookManager?.triggerTaskError({
                    taskId: execCtx.taskId,
                    error: err,
                    timestamp: Date.now(),
                    recoverable: false,
                });

                const result: TaskResult = {
                    success: false,
                    response: `任务执行失败: ${err.message}`,
                    tier: 'smart',
                    executionTime: Date.now() - startTime,
                };

                await this.hookManager?.triggerTaskComplete({
                    taskId: execCtx.taskId,
                    result,
                    timestamp: Date.now(),
                    duration: result.executionTime,
                    sessionId: execCtx.sessionId,
                    traceId: traceCtx.traceId,
                });

                return result;
            }
        });
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
    private async executeSimple(input: string, analysis: TaskAnalysis, execCtx: ExecutionContext): Promise<TaskResult> {
        // 1. 如果有直达匹配，直接执行
        if (analysis.directToolCall) {
            console.log(`[TaskOrchestrator] Direct tool call: ${analysis.directToolCall.tool}.${analysis.directToolCall.action}`);
            try {
                const result = await this.toolExecutor.execute(analysis.directToolCall, execCtx);
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
        return this.executeFastLayer(input, execCtx);
    }

    /**
     * Fast 层执行
     */
    private async executeFastLayer(input: string, execCtx?: ExecutionContext): Promise<TaskResult> {
        try {
            // 获取对话历史
            const history = this.contextManager.getMessagesForAI(5);

            // 构建系统提示词（包含项目记忆和技能摘要）
            const systemPrompt = this.buildSystemPrompt();
            const skillContext = this.loadMatchingSkills(input);

            const messages: Message[] = [
                // 注入系统上下文
                ...(systemPrompt ? [{ role: 'system' as const, content: systemPrompt }] : []),
                ...(skillContext ? [{ role: 'system' as const, content: '## Skill Instructions\\n' + skillContext }] : []),
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
                }, execCtx);

                return {
                    success: toolResult.success,
                    response: toolResult.message || response.content || '操作完成',
                    tier: 'fast',
                    executionTime: 0,
                    model: this.fastEngine.name,
                    usage: response.usage,
                };
            }

            return {
                success: true,
                response: response.content,
                tier: 'fast',
                executionTime: 0,
                model: this.fastEngine.name,
                usage: response.usage,
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
    private async executeVisual(input: string, analysis: TaskAnalysis, execCtx: ExecutionContext): Promise<TaskResult> {
        try {
            console.log('[TaskOrchestrator] Executing visual task...');

            // 1. Vision 层分析屏幕
            const visionPrompt = analysis.visionPrompt || `分析屏幕并执行: ${input}`;

            const screenshotBase64 = await this.captureScreenshotBase64();
            const history = this.contextManager.getMessagesForAI(5) as Message[];
            const visionResponse = await this.visionEngine.chat([
                ...history,
                { role: 'user', content: visionPrompt, ...(screenshotBase64 ? { images: [screenshotBase64] } : {}) },
            ]);

            // 2. 检查是否需要执行操作
            const actionMatch = visionResponse.content.match(/\[ACTION\]\s*(\{[\s\S]*?\})/);
            if (actionMatch) {
                try {
                    const action = JSON.parse(actionMatch[1]);
                    const actionResult = await this.toolExecutor.executeAction(action, execCtx);
                    return {
                        success: actionResult.success,
                        response: actionResult.message || '视觉操作完成',
                        tier: 'vision',
                        executionTime: 0,
                        model: this.visionEngine.name,
                        usage: visionResponse.usage,
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
                usage: visionResponse.usage,
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
    private async executeComplex(input: string, _analysis: TaskAnalysis, execCtx: ExecutionContext): Promise<TaskResult> {
        try {
            console.log('[TaskOrchestrator] Executing complex task...');

            // Phase 8: O-W 模式 - 任务分解并行执行
            if (this.enableOW && this.taskDecomposer && this.workerPool) {
                console.log('[TaskOrchestrator] Using Orchestrator-Worker pattern...');
                const decomposition = this.taskDecomposer.decompose(input);

                // 如果有多个子任务且非严格顺序，使用并行执行
                if (decomposition.subTasks.length > 1 && decomposition.strategy !== 'sequential') {
                    console.log(`[TaskOrchestrator] Parallel executing ${decomposition.subTasks.length} subtasks...`);
                    const results = await this.workerPool.executeParallel(decomposition.subTasks);
                    const outputs = Array.from(results.values()).map(r => String(r));

                    // 汇总结果
                    const summary = await this.taskPlanner.summarize(input, outputs.map((o, i) => ({
                        stepId: i,
                        success: !o.startsWith('error'),
                        output: o,
                    })));

                    return {
                        success: true,
                        response: summary,
                        tier: 'smart',
                        executionTime: 0,
                        model: this.smartEngine.name,
                    };
                }
            }

            // Phase 6: 使用 ReAct 循环执行
            if (this.enableReAct && this.reActOrchestrator) {
                console.log('[TaskOrchestrator] Using ReAct orchestrator...');
                const taskId = execCtx.taskId;

                // 创建动作执行器
                const executor = async (action: string, params: Record<string, unknown>): Promise<string> => {
                    // 尝试解析为工具调用
                    const toolMatch = action.match(/^(\w+)\.(\w+)$/);
                    if (toolMatch) {
                        const [, tool, actionName] = toolMatch;
                        const result = await this.toolExecutor.execute({
                            tool,
                            action: actionName,
                            params,
                        }, execCtx);
                        return result.success
                            ? JSON.stringify(result.data ?? result.message)
                            : `Error: ${result.message}`;
                    }
                    // 否则使用 Fast 层处理
                    const fastResult = await this.executeFastLayer(action, execCtx);
                    return fastResult.response;
                };

                const reactResult = await this.reActOrchestrator.execute(taskId, input, executor);

                return {
                    success: reactResult.success,
                    response: reactResult.result,
                    tier: 'smart',
                    executionTime: 0,
                    model: this.smartEngine.name,
                };
            }

            // 传统执行: Smart 层生成执行计划
            const tools = this.toolExecutor.getAvailableTools();
            const plan = await this.taskPlanner.planTask(input, tools);
            console.log(`[TaskOrchestrator] Plan generated: ${plan.steps.length} steps`);

            await this.hookManager?.triggerProgress({
                taskId: execCtx.taskId,
                currentStep: 0,
                totalSteps: plan.steps.length,
                percentage: 0,
                stepDescription: '已生成执行计划',
            });

            // 2. 按步骤执行
            const stepResults: StepResult[] = [];
            for (const [index, step] of plan.steps.entries()) {
                console.log(`[TaskOrchestrator] Executing step ${step.id}: ${step.description}`);

                await this.hookManager?.triggerProgress({
                    taskId: execCtx.taskId,
                    currentStep: index,
                    totalSteps: plan.steps.length,
                    percentage: Math.round((index / Math.max(plan.steps.length, 1)) * 100),
                    stepDescription: step.description,
                });

                const result = await this.executeStep(step, execCtx);
                stepResults.push(result);

                await this.hookManager?.triggerProgress({
                    taskId: execCtx.taskId,
                    currentStep: index + 1,
                    totalSteps: plan.steps.length,
                    percentage: Math.round(((index + 1) / Math.max(plan.steps.length, 1)) * 100),
                    stepDescription: result.success ? '步骤完成' : '步骤失败',
                });

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
    private async executeStep(step: ExecutionStep, execCtx: ExecutionContext): Promise<StepResult> {
        try {
            // 视觉步骤
            if (step.requiresVision) {
                const screenshotBase64 = await this.captureScreenshotBase64();
                const visionResult = await this.visionEngine.chat([
                    { role: 'user', content: step.description, ...(screenshotBase64 ? { images: [screenshotBase64] } : {}) },
                ]);
                return {
                    stepId: step.id,
                    success: true,
                    output: visionResult.content,
                };
            }

            // 工具步骤
            const actionSpec = step.action.trim();
            if (!actionSpec) {
                return {
                    stepId: step.id,
                    success: false,
                    error: new Error('步骤缺少 action'),
                };
            }

            // action 支持两种格式：
            // 1) tool_name（推荐，例如 audio_set_volume）
            // 2) adapterId.capabilityId（例如 com.aios.adapter.audio.set_volume）
            let tool = actionSpec;
            let action = '';
            const lastDot = actionSpec.lastIndexOf('.');
            if (lastDot > 0 && lastDot < actionSpec.length - 1) {
                tool = actionSpec.slice(0, lastDot);
                action = actionSpec.slice(lastDot + 1);
            }

            // Phase 8: 高危操作检查和确认
            if (this.enableConfirmation && this.confirmationManager) {
                const riskCheck = promptGuard.checkAndLog(step.description, 'executeStep');
                if (riskCheck.riskLevel === 'high' || riskCheck.riskLevel === 'medium') {
                    const approved = await this.confirmationManager.requestConfirmation({
                        taskId: `step-${step.id}`,
                        action: step.description,
                        riskLevel: riskCheck.riskLevel as 'medium' | 'high',
                        details: {
                            tool,
                            action,
                            params: step.params,
                            patterns: riskCheck.patterns,
                        },
                    });

                    if (!approved) {
                        return {
                            stepId: step.id,
                            success: false,
                            error: new Error('用户拒绝执行此高危操作'),
                        };
                    }
                }
            }

            const result = await this.toolExecutor.execute({
                tool,
                action,
                params: step.params,
            }, execCtx);

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
