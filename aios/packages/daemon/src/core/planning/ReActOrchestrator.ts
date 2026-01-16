/**
 * ReActOrchestrator - ReAct 循环编排器
 * 实现 感知 → 规划 → 决策 → 执行 → 观察 → 反思 循环
 */

import type {
    ReActState,
    ReflectionResult,
    TaskPlan,
    PlanStep,
} from './types.js';
import { PlanManager } from './PlanManager.js';

/**
 * ReAct 编排器配置
 */
export interface ReActConfig {
    /** 最大循环次数 */
    maxIterations?: number;
    /** 是否启用详细日志 */
    verbose?: boolean;
    /** 反思阈值（连续失败多少次触发重规划） */
    replanThreshold?: number;
}

/**
 * ReAct 执行上下文
 */
export interface ReActContext {
    /** 任务 ID */
    taskId: string;
    /** 用户输入 */
    input: string;
    /** 当前计划 */
    plan: TaskPlan;
    /** 循环状态 */
    state: ReActState;
    /** 累积的观察结果 */
    observations: string[];
    /** 连续失败次数 */
    consecutiveFailures: number;
}

/**
 * 执行动作函数
 */
export type ActionExecutor = (action: string, params: Record<string, unknown>) => Promise<string>;

/**
 * AI 引擎接口 (简化版)
 */
export interface AIEngine {
    chat(messages: unknown[]): Promise<string>;
}

/**
 * ReAct 循环编排器
 */
export class ReActOrchestrator {
    private smartEngine: AIEngine;
    private planManager: PlanManager;
    private config: Required<ReActConfig>;

    constructor(
        smartEngine: AIEngine,
        planManager: PlanManager,
        config: ReActConfig = {}
    ) {
        this.smartEngine = smartEngine;
        this.planManager = planManager;
        this.config = {
            maxIterations: config.maxIterations ?? 10,
            verbose: config.verbose ?? false,
            replanThreshold: config.replanThreshold ?? 3,
        };
    }

    /**
     * 执行 ReAct 循环
     */
    async execute(
        taskId: string,
        input: string,
        executor: ActionExecutor
    ): Promise<{ success: boolean; result: string; iterations: number }> {
        // 创建或获取计划
        const plan = this.planManager.getOrCreatePlan(taskId, input);

        // 如果没有步骤，先分解任务
        if (plan.steps.length === 0) {
            const steps = await this.decompose(input);
            plan.steps = steps;
            plan.updatedAt = Date.now();
        }

        // 初始化状态
        const context: ReActContext = {
            taskId,
            input,
            plan,
            state: {
                phase: 'perceive',
                iteration: 0,
                maxIterations: this.config.maxIterations,
            },
            observations: [],
            consecutiveFailures: 0,
        };

        // 执行循环
        while (context.state.iteration < this.config.maxIterations) {
            context.state.iteration++;
            this.log(`[ReAct] Iteration ${context.state.iteration}/${this.config.maxIterations}`);

            try {
                // 1. 感知 (Perceive)
                context.state.phase = 'perceive';
                const perception = await this.perceive(context);
                context.state.perception = perception;

                // 2. 规划 (Plan) - 检查当前计划是否需要调整
                context.state.phase = 'plan';
                await this.checkAndAdjustPlan(context);

                // 3. 决策 (Decide)
                context.state.phase = 'decide';
                const decision = await this.decide(context);
                context.state.decision = decision.action;

                if (decision.shouldComplete) {
                    return {
                        success: true,
                        result: decision.result || '任务完成',
                        iterations: context.state.iteration,
                    };
                }

                // 4. 执行 (Execute)
                context.state.phase = 'execute';
                const actionResult = await executor(decision.action, decision.params);
                context.state.action = decision.action;

                // 5. 观察 (Observe)
                context.state.phase = 'observe';
                context.state.observation = actionResult;
                context.observations.push(actionResult);

                // 6. 反思 (Reflect)
                context.state.phase = 'reflect';
                const reflection = await this.reflect(context, actionResult);
                context.state.reflection = reflection;

                // 根据反思结果决定下一步
                if (reflection.success) {
                    context.consecutiveFailures = 0;
                    // 标记当前步骤完成
                    if (plan.currentStepIndex < plan.steps.length) {
                        this.planManager.completeStep(taskId, plan.steps[plan.currentStepIndex].id, actionResult);
                    }
                } else {
                    context.consecutiveFailures++;

                    if (reflection.nextAction === 'complete') {
                        return {
                            success: false,
                            result: reflection.reason,
                            iterations: context.state.iteration,
                        };
                    }

                    if (reflection.nextAction === 'replan' ||
                        context.consecutiveFailures >= this.config.replanThreshold) {
                        await this.replan(context, reflection.reason);
                        context.consecutiveFailures = 0;
                    }
                }

                // 检查是否所有步骤完成
                if (plan.currentStepIndex >= plan.steps.length) {
                    return {
                        success: true,
                        result: await this.summarize(context),
                        iterations: context.state.iteration,
                    };
                }

            } catch (error) {
                const err = error instanceof Error ? error : new Error(String(error));
                this.log(`[ReAct] Error in iteration: ${err.message}`);
                context.consecutiveFailures++;

                if (context.consecutiveFailures >= this.config.replanThreshold) {
                    this.planManager.addIssue(taskId, err.message, 'high');
                }
            }
        }

        return {
            success: false,
            result: '达到最大循环次数限制',
            iterations: context.state.iteration,
        };
    }

    /**
     * 感知当前状态
     */
    private async perceive(context: ReActContext): Promise<string> {
        const summary = this.planManager.getPlanSummary(context.taskId);
        const recentObservations = context.observations.slice(-3).join('\n');

        return `Current Goal: ${context.plan.goal}
Plan Progress: ${summary}
Recent Observations: ${recentObservations || 'None'}`;
    }

    /**
     * 检查并调整计划
     */
    private async checkAndAdjustPlan(context: ReActContext): Promise<void> {
        // 如果有太多失败，可能需要重新规划
        const failedSteps = context.plan.steps.filter(s => s.status === 'failed');
        if (failedSteps.length > 2) {
            this.log('[ReAct] Multiple failed steps detected, considering replan');
        }
    }

    /**
     * 决策下一步动作
     */
    private async decide(context: ReActContext): Promise<{
        action: string;
        params: Record<string, unknown>;
        shouldComplete: boolean;
        result?: string;
    }> {
        const currentStep = context.plan.steps[context.plan.currentStepIndex];

        if (!currentStep) {
            return {
                action: 'complete',
                params: {},
                shouldComplete: true,
                result: '所有步骤已完成',
            };
        }

        // 标记步骤开始
        this.planManager.startStep(context.taskId, currentStep.id);

        return {
            action: currentStep.description,
            params: { stepId: currentStep.id },
            shouldComplete: false,
        };
    }

    /**
     * 反思执行结果
     */
    private async reflect(context: ReActContext, result: string): Promise<ReflectionResult> {
        // 简单的反思逻辑：检查结果是否包含错误指示
        const isError = result.toLowerCase().includes('error') ||
            result.toLowerCase().includes('failed') ||
            result.toLowerCase().includes('exception');

        if (isError) {
            return {
                success: false,
                reason: `执行失败: ${result}`,
                nextAction: context.consecutiveFailures >= 2 ? 'replan' : 'retry',
                lessons: ['需要检查执行参数', '可能需要调整方法'],
            };
        }

        return {
            success: true,
            reason: '步骤执行成功',
            nextAction: 'continue',
        };
    }

    /**
     * 重新规划
     */
    private async replan(context: ReActContext, reason: string): Promise<void> {
        this.log(`[ReAct] Replanning due to: ${reason}`);

        // 记录问题
        this.planManager.addIssue(context.taskId, reason, 'medium');

        // 获取剩余步骤并重新调整
        const remainingSteps = context.plan.steps
            .slice(context.plan.currentStepIndex)
            .filter(s => s.status !== 'completed');

        // 简单策略：跳过失败的步骤
        if (remainingSteps.length > 0 && remainingSteps[0].status === 'failed') {
            this.planManager.updateStep(context.taskId, remainingSteps[0].id, { status: 'skipped' });
        }
    }

    /**
     * 分解任务为步骤（使用 AI）
     */
    private async decompose(goal: string): Promise<PlanStep[]> {
        // 尝试使用 AI 分解任务
        try {
            const prompt = `请将以下任务分解为具体的执行步骤（JSON数组格式）：

任务: ${goal}

返回格式:
[
  {"id": 1, "description": "步骤描述", "dependsOn": []},
  {"id": 2, "description": "步骤描述", "dependsOn": [1]}
]

只返回JSON数组，不要其他内容。`;

            const response = await this.smartEngine.chat([
                { role: 'user', content: prompt }
            ]);

            // 尝试解析 AI 响应
            const jsonMatch = response.match(/\[[\s\S]*\]/);
            if (jsonMatch) {
                const parsed = JSON.parse(jsonMatch[0]);
                return parsed.map((step: any) => ({
                    id: step.id,
                    description: step.description,
                    dependsOn: step.dependsOn || [],
                    status: 'pending' as const,
                }));
            }
        } catch (error) {
            this.log(`[ReAct] AI decomposition failed, using fallback: ${error}`);
        }

        // 降级：创建基本步骤
        const steps: PlanStep[] = [
            {
                id: 1,
                description: `分析任务: ${goal}`,
                status: 'pending',
            },
            {
                id: 2,
                description: '执行核心操作',
                status: 'pending',
                dependsOn: [1],
            },
            {
                id: 3,
                description: '验证结果',
                status: 'pending',
                dependsOn: [2],
            },
        ];

        return steps;
    }

    /**
     * AI 增强的反思
     */
    private async reflectWithAI(context: ReActContext, result: string): Promise<ReflectionResult> {
        try {
            const prompt = `分析以下执行结果，判断是否成功并给出建议：

任务目标: ${context.plan.goal}
当前步骤: ${context.plan.steps[context.plan.currentStepIndex]?.description || '无'}
执行结果: ${result.substring(0, 500)}
连续失败次数: ${context.consecutiveFailures}

请以JSON格式返回：
{
  "success": true|false,
  "reason": "原因分析",
  "nextAction": "continue|retry|replan|complete",
  "lessons": ["学习点1", "学习点2"]
}`;

            const response = await this.smartEngine.chat([
                { role: 'user', content: prompt }
            ]);

            const jsonMatch = response.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                return JSON.parse(jsonMatch[0]);
            }
        } catch (error) {
            this.log(`[ReAct] AI reflection failed, using fallback: ${error}`);
        }

        // 降级到规则反思
        return this.reflect(context, result);
    }

    /**
     * 总结执行结果
     */
    private async summarize(context: ReActContext): Promise<string> {
        const completed = context.plan.steps.filter(s => s.status === 'completed');
        const results = completed.map(s => s.result).filter(Boolean);

        return `任务完成: ${context.plan.goal}
完成 ${completed.length}/${context.plan.steps.length} 个步骤
结果摘要: ${results.join('; ') || '任务已成功执行'}`;
    }

    /**
     * 日志输出
     */
    private log(message: string): void {
        if (this.config.verbose) {
            console.log(message);
        }
    }
}
