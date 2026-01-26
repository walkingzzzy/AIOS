/**
 * 任务编排器
 * 三层 AI 协调的核心：意图分析 → 任务路由 → 执行 → 汇总
 */

import type { IAIEngine, Message, ToolCall, ToolDefinition, StreamChunk } from '@aios/shared';
import { createStreamProcessingState, mergeToolCallDelta, toOpenAIToolDefinition } from '@aios/shared';
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
    type ExecutionPlan,
} from '../types/orchestrator.js';
import { SkillRegistry } from './skills/SkillRegistry.js';
import { ProjectMemoryManager } from './skills/ProjectMemoryManager.js';
import { WorkerPool, type WorkerExecutor } from './orchestration/WorkerPool.js';
import { TaskDecomposer } from './orchestration/TaskDecomposer.js';
import type { HookManager, PrepareRequestContext } from './hooks/index.js';
import { traceContextManager } from './trace/index.js';
import { PlanConfirmationManager } from './planning/PlanConfirmationManager.js';
import type { PlanDraft, PlanApprovalResponse } from '../types/orchestrator.js';

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
    /** 是否启用计划确认流程（复杂任务执行前需用户确认） */
    enablePlanConfirmation?: boolean;
    /** 计划确认超时时间 (ms)，默认 5 分钟 */
    planConfirmationTimeout?: number;
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

    // Plan Confirmation Workflow
    private planConfirmationManager: PlanConfirmationManager;
    private enablePlanConfirmation: boolean;
    private planConfirmationTimeout: number;

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

        // Plan Confirmation Workflow - 计划确认流程
        this.enablePlanConfirmation = config.enablePlanConfirmation ?? false;
        this.planConfirmationTimeout = config.planConfirmationTimeout ?? 5 * 60 * 1000; // 5 minutes
        this.planConfirmationManager = new PlanConfirmationManager({
            defaultTimeout: this.planConfirmationTimeout,
            autoRiskAssessment: true,
        });
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
                this.contextManager.addMessage({ role: 'user', content: input }, execCtx.sessionId);
                this.contextManager.addMessage({ role: 'assistant', content: result.response }, execCtx.sessionId);

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
     * 流式处理用户请求
     * 实时输出 AI 响应内容，适用于需要即时反馈的场景
     */
    async *processStream(
        input: string,
        context: TaskContext = {}
    ): AsyncGenerator<StreamChunk, TaskResult, unknown> {
        const startTime = Date.now();
        const execCtx: ExecutionContext = {
            taskId: context.taskId ?? `task_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
            sessionId: context.sessionId,
        };

        try {
            console.log(`[TaskOrchestrator] Stream processing: "${input.substring(0, 50)}..."`);

            // 1. 分析任务类型
            const analysis = await this.analyzeWithCache(input, context);
            console.log(`[TaskOrchestrator] Task type: ${analysis.taskType}, confidence: ${analysis.confidence}`);

            await this.hookManager?.triggerTaskStart({
                taskId: execCtx.taskId,
                input,
                analysis,
                timestamp: startTime,
            });

            // 2. 流式执行 (目前仅支持 Simple 任务的流式输出)
            if (analysis.taskType === TaskType.Simple && !analysis.directToolCall) {
                // 使用 Fast 层流式处理
                let fullContent = '';

                for await (const chunk of this.executeFastLayerStream(input, execCtx, context.abortSignal)) {
                    yield chunk;
                    if (chunk.content) {
                        fullContent += chunk.content;
                    }
                }

                // 保存到对话历史
                this.contextManager.addMessage({ role: 'user', content: input }, execCtx.sessionId);
                this.contextManager.addMessage({ role: 'assistant', content: fullContent }, execCtx.sessionId);

                const result: TaskResult = {
                    success: true,
                    response: fullContent,
                    tier: 'fast',
                    executionTime: Date.now() - startTime,
                    model: this.fastEngine.name,
                };

                await this.hookManager?.triggerTaskComplete({
                    taskId: execCtx.taskId,
                    result,
                    timestamp: Date.now(),
                    duration: result.executionTime,
                    sessionId: execCtx.sessionId,
                });

                return result;
            }

            // 3. 非流式任务回退到同步处理
            const result = await this.process(input, context);
            yield { content: result.response, finishReason: 'stop' };
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

            yield { content: result.response, finishReason: 'stop' };
            return result;
        }
    }

    /**
     * Fast 层流式执行
     */
    private async *executeFastLayerStream(
        input: string,
        execCtx?: ExecutionContext,
        signal?: AbortSignal
    ): AsyncGenerator<StreamChunk, void, unknown> {
        // 获取对话历史
        const history = this.contextManager.getMessagesForAI(5, execCtx?.sessionId);

        // 构建系统提示词
        const systemPrompt = this.buildSystemPrompt();
        const skillContext = this.loadMatchingSkills(input);

        const messages: Message[] = [
            ...(systemPrompt ? [{ role: 'system' as const, content: systemPrompt }] : []),
            ...(skillContext ? [{ role: 'system' as const, content: '## Skill Instructions\\n' + skillContext }] : []),
            ...history,
            { role: 'user', content: input },
        ];

        // 获取可用工具
        const internalTools = this.toolExecutor.getAvailableTools();
        const tools: ToolDefinition[] = internalTools.slice(0, 20).map(t => toOpenAIToolDefinition(t));

        // 生成请求 ID
        const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        const requestStartTime = Date.now();

        // 触发 PrepareRequest 钩子 - 允许 Hook 修改请求消息
        const prepareCtx: PrepareRequestContext = {
            requestId,
            engineId: this.fastEngine.id,
            messages: messages.map(m => ({ role: m.role, content: String(m.content) })),
            options: { stream: true },
            mutableMessages: messages.map(m => ({ role: m.role, content: String(m.content) })),
            mutableOptions: { stream: true },
        };
        await this.hookManager?.triggerPrepareRequest(prepareCtx);

        // 使用修改后的消息
        const finalMessages: Message[] = prepareCtx.mutableMessages.map(m => ({
            role: m.role as 'system' | 'user' | 'assistant',
            content: m.content,
        }));

        // 触发 LLM 请求钩子（流式）
        await this.hookManager?.triggerLLMRequest({
            requestId,
            taskId: execCtx?.taskId,
            engineId: this.fastEngine.id,
            model: this.fastEngine.model,
            messages: finalMessages.map(m => ({ role: m.role, content: m.content })),
            options: { stream: true },
            tools: tools.map(t => ({ name: t.function.name, description: t.function.description })),
            timestamp: requestStartTime,
        });

        let chunkIndex = 0;
        const streamState = createStreamProcessingState();

        // 检查引擎是否支持流式
        if (this.fastEngine.supportsStreaming()) {
            // 使用真正的流式 API
            for await (const chunk of this.fastEngine.chatStreamWithTools(finalMessages, tools, { signal })) {
                // 触发流式块钩子
                await this.hookManager?.triggerLLMStreamChunk({
                    requestId,
                    taskId: execCtx?.taskId,
                    engineId: this.fastEngine.id,
                    content: chunk.content,
                    reasoningContent: chunk.reasoningContent,
                    toolCalls: chunk.toolCalls?.map(tc => ({
                        index: tc.index,
                        id: tc.id,
                        name: tc.function?.name,
                        arguments: tc.function?.arguments,
                    })),
                    finished: chunk.finishReason !== null && chunk.finishReason !== undefined,
                    finishReason: chunk.finishReason,
                    chunkIndex: chunkIndex++,
                    timestamp: Date.now(),
                });

                if (chunk.content) {
                    streamState.contentBuffer += chunk.content;
                }
                if (chunk.toolCalls) {
                    for (const delta of chunk.toolCalls) {
                        mergeToolCallDelta(streamState, delta);
                    }
                }

                if (chunk.finishReason === 'tool_calls') {
                    const toolCalls = Array.from(streamState.toolCalls.values());
                    if (toolCalls.length > 0) {
                        console.log(`[TaskOrchestrator] Stream tool call(s): ${toolCalls.map(c => c.function.name).join(', ')}`);
                        const toolResults = await this.executeToolCalls(toolCalls, execCtx);
                        const followUpMessages: Message[] = [
                            ...finalMessages,
                            ...(streamState.contentBuffer ? [{ role: 'assistant' as const, content: streamState.contentBuffer }] : []),
                            {
                                role: 'user',
                                content: `以下是工具执行结果：\n${this.formatToolResults(toolResults)}\n请基于结果完成回复。`,
                            },
                        ];
                        const followUp = await this.fastEngine.chat(followUpMessages);
                        yield { content: followUp.content, finishReason: followUp.finishReason ?? 'stop', usage: followUp.usage };
                        return;
                    }
                }

                yield chunk;
            }
        } else {
            // 回退到非流式（一次性返回）
            const response = await this.fastEngine.chatWithTools(finalMessages, tools);
            yield { content: response.content, finishReason: 'stop' };
        }
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

    private parseToolName(name: string): { tool: string; action: string } {
        if (name.includes('_')) {
            return { tool: name, action: '' };
        }
        const lastDot = name.lastIndexOf('.');
        if (lastDot > 0 && lastDot < name.length - 1) {
            return {
                tool: name.slice(0, lastDot),
                action: name.slice(lastDot + 1),
            };
        }
        return { tool: name, action: '' };
    }

    private safeParseParams(raw: string | undefined): Record<string, unknown> {
        if (!raw) return {};
        try {
            const parsed = JSON.parse(raw) as unknown;
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                return parsed as Record<string, unknown>;
            }
        } catch {
            // ignore
        }
        return {};
    }

    private formatToolResults(results: Array<{ name: string; success: boolean; message?: string; data?: unknown }>): string {
        return results.map((r) => {
            const payload = r.data !== undefined ? JSON.stringify(r.data) : '';
            return `- ${r.name}: ${r.success ? '成功' : '失败'}${r.message ? ` (${r.message})` : ''}${payload ? ` -> ${payload}` : ''}`;
        }).join('\n');
    }

    private async executeToolCalls(toolCalls: ToolCall[], execCtx?: ExecutionContext): Promise<Array<{
        name: string;
        success: boolean;
        message?: string;
        data?: unknown;
    }>> {
        const results: Array<{ name: string; success: boolean; message?: string; data?: unknown }> = [];
        for (const call of toolCalls) {
            const { tool, action } = this.parseToolName(call.function.name);
            const params = this.safeParseParams(call.function.arguments);
            const result = await this.toolExecutor.execute({ tool, action, params }, execCtx);
            results.push({
                name: call.function.name,
                success: result.success,
                message: result.message,
                data: result.data,
            });
        }
        return results;
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
            const history = this.contextManager.getMessagesForAI(5, execCtx?.sessionId);

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

            // 生成请求 ID
            const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
            const requestStartTime = Date.now();

            // 触发 PrepareRequest 钩子 - 允许 Hook 修改请求消息
            const prepareCtx: PrepareRequestContext = {
                requestId,
                engineId: this.fastEngine.id,
                messages: messages.map(m => ({ role: m.role, content: String(m.content) })),
                options: { stream: false },
                mutableMessages: messages.map(m => ({ role: m.role, content: String(m.content) })),
                mutableOptions: { stream: false },
            };
            await this.hookManager?.triggerPrepareRequest(prepareCtx);

            // 使用修改后的消息
            const finalMessages: Message[] = prepareCtx.mutableMessages.map(m => ({
                role: m.role as 'system' | 'user' | 'assistant',
                content: m.content,
            }));

            // 触发 LLM 请求钩子
            await this.hookManager?.triggerLLMRequest({
                requestId,
                taskId: execCtx?.taskId,
                engineId: this.fastEngine.id,
                model: this.fastEngine.model,
                messages: finalMessages.map(m => ({ role: m.role, content: m.content })),
                options: { stream: false },
                tools: tools.map(t => ({ name: t.function.name, description: t.function.description })),
                timestamp: requestStartTime,
            });

            // 调用 Fast 层 AI（带工具）
            const response = await this.fastEngine.chatWithTools(finalMessages, tools);

            // 触发 LLM 响应钩子
            await this.hookManager?.triggerLLMResponse({
                requestId,
                taskId: execCtx?.taskId,
                engineId: this.fastEngine.id,
                model: this.fastEngine.model,
                content: response.content,
                finishReason: response.finishReason,
                toolCalls: response.toolCalls?.map(tc => ({
                    id: tc.id,
                    name: tc.function.name,
                    arguments: tc.function.arguments,
                })),
                usage: response.usage,
                timestamp: Date.now(),
                latency: Date.now() - requestStartTime,
            });

            // 如果有工具调用
            if (response.toolCalls && response.toolCalls.length > 0) {
                console.log(`[TaskOrchestrator] Fast layer tool call(s): ${response.toolCalls.map(c => c.function.name).join(', ')}`);

                const toolResults = await this.executeToolCalls(response.toolCalls, execCtx);
                const followUpMessages: Message[] = [
                    ...finalMessages,
                    ...(response.content ? [{ role: 'assistant' as const, content: response.content }] : []),
                    {
                        role: 'user',
                        content: `以下是工具执行结果：\n${this.formatToolResults(toolResults)}\n请基于结果完成回复。`,
                    },
                ];

                const followUp = await this.fastEngine.chat(followUpMessages);

                return {
                    success: toolResults.every(r => r.success),
                    response: followUp.content || response.content || '操作完成',
                    tier: 'fast',
                    executionTime: 0,
                    model: this.fastEngine.name,
                    usage: followUp.usage ?? response.usage,
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
            const history = this.contextManager.getMessagesForAI(5, execCtx.sessionId) as Message[];
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

            // 如果启用计划确认，使用详细规划
            let plan: ExecutionPlan;
            let planDraft: PlanDraft | undefined;

            if (this.enablePlanConfirmation) {
                planDraft = await this.taskPlanner.planTaskDetailed(execCtx.taskId, input, tools);
                plan = planDraft;
                console.log(`[TaskOrchestrator] Detailed plan generated: ${plan.steps.length} steps, risks: ${planDraft.risks.length}`);

                // 检查是否需要用户确认
                if (this.isPlanSignificant(planDraft)) {
                    console.log(`[TaskOrchestrator] Plan requires user approval...`);

                    // 发送审批请求事件
                    this.emitPlanApprovalRequired(execCtx.taskId, planDraft);

                    try {
                        // 等待用户确认
                        const approval = await this.planConfirmationManager.submitForApproval(
                            execCtx.taskId,
                            planDraft,
                            this.planConfirmationTimeout
                        );

                        if (!approval.approved) {
                            console.log(`[TaskOrchestrator] Plan rejected by user`);
                            return {
                                success: false,
                                response: approval.feedback || '用户取消了计划执行',
                                tier: 'smart',
                                executionTime: 0,
                            };
                        }

                        // 如果用户修改了计划
                        if (approval.modifiedSteps && approval.modifiedSteps.length > 0) {
                            plan = { ...plan, steps: approval.modifiedSteps };
                            console.log(`[TaskOrchestrator] Plan modified by user, ${plan.steps.length} steps`);
                        }

                        console.log(`[TaskOrchestrator] Plan approved, proceeding with execution`);
                    } catch (error) {
                        console.error('[TaskOrchestrator] Plan approval failed:', error);
                        return {
                            success: false,
                            response: `计划确认超时或失败: ${error instanceof Error ? error.message : '未知错误'}`,
                            tier: 'smart',
                            executionTime: 0,
                        };
                    }
                }
            } else {
                plan = await this.taskPlanner.planTask(input, tools);
            }

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
        // 发送步骤开始事件
        this.emitStepEvent('step:started', {
            taskId: execCtx.taskId,
            stepId: step.id,
            description: step.description,
            timestamp: Date.now(),
        });

        try {
            // 视觉步骤
            if (step.requiresVision) {
                const screenshotBase64 = await this.captureScreenshotBase64();
                const visionResult = await this.visionEngine.chat([
                    { role: 'user', content: step.description, ...(screenshotBase64 ? { images: [screenshotBase64] } : {}) },
                ]);

                // 发送步骤完成事件
                this.emitStepEvent('step:completed', {
                    taskId: execCtx.taskId,
                    stepId: step.id,
                    success: true,
                    output: visionResult.content,
                    timestamp: Date.now(),
                });

                return {
                    stepId: step.id,
                    success: true,
                    output: visionResult.content,
                };
            }

            // 工具步骤
            const actionSpec = step.action.trim();
            if (!actionSpec) {
                // 发送步骤失败事件
                this.emitStepEvent('step:failed', {
                    taskId: execCtx.taskId,
                    stepId: step.id,
                    error: '步骤缺少 action',
                    timestamp: Date.now(),
                });

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
                        // 发送步骤失败事件
                        this.emitStepEvent('step:failed', {
                            taskId: execCtx.taskId,
                            stepId: step.id,
                            error: '用户拒绝执行此高危操作',
                            timestamp: Date.now(),
                        });

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

            // 发送步骤完成/失败事件
            if (result.success) {
                this.emitStepEvent('step:completed', {
                    taskId: execCtx.taskId,
                    stepId: step.id,
                    success: true,
                    output: result.data,
                    timestamp: Date.now(),
                });
            } else {
                this.emitStepEvent('step:failed', {
                    taskId: execCtx.taskId,
                    stepId: step.id,
                    error: result.message || '执行失败',
                    timestamp: Date.now(),
                });
            }

            return {
                stepId: step.id,
                success: result.success,
                output: result.data,
                error: result.success ? undefined : new Error(result.message),
            };
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);

            // 发送步骤失败事件
            this.emitStepEvent('step:failed', {
                taskId: execCtx.taskId,
                stepId: step.id,
                error: errorMessage,
                timestamp: Date.now(),
            });

            return {
                stepId: step.id,
                success: false,
                error: error instanceof Error ? error : new Error(String(error)),
            };
        }
    }

    /**
     * 发送步骤级事件到前端
     */
    private emitStepEvent(method: string, params: unknown): void {
        const notification = {
            jsonrpc: '2.0',
            method,
            params,
        };

        try {
            process.stdout.write(JSON.stringify(notification) + '\n');
        } catch (error) {
            console.error(`[TaskOrchestrator] Failed to emit ${method}:`, error);
        }
    }

    // =========================================================================
    // Plan Confirmation Workflow 辅助方法
    // =========================================================================

    /**
     * 判断计划是否需要用户确认
     * 根据步骤数量、风险级别和所需权限判断
     */
    private isPlanSignificant(plan: PlanDraft): boolean {
        // 超过 2 个步骤需要确认
        if (plan.steps.length > 2) {
            return true;
        }
        // 存在中/高风险需要确认
        if (plan.risks.some(r => r.level === 'medium' || r.level === 'high')) {
            return true;
        }
        // 需要敏感权限需要确认
        if (plan.requiredPermissions.length > 0) {
            return true;
        }
        return false;
    }

    /**
     * 发送计划审批请求事件
     * 通过 stdout JSON-RPC notification 发送给前端
     */
    private emitPlanApprovalRequired(taskId: string, draft: PlanDraft): void {
        // Plan confirmation manager 会在 submitForApproval 时触发 plan.approval_required 事件
        // 这里我们通过 console.log 触发额外通知（daemon 中 emitNotification 在 index.ts 中）
        // 实际上 PlanConfirmationManager.emitPlanEvent 已经处理了事件发送
        // 但我们需要通过 stdout 发送给 Electron client

        const notification = {
            jsonrpc: '2.0',
            method: 'plan:approval-required',
            params: draft,
        };

        try {
            process.stdout.write(JSON.stringify(notification) + '\n');
        } catch (error) {
            console.error('[TaskOrchestrator] Failed to emit plan approval notification:', error);
        }

        console.log(`[TaskOrchestrator] Emitted plan:approval-required for draft ${draft.draftId}`);
    }
}
