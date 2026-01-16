/**
 * PLAN.md + ReAct 循环模块类型定义
 */

/**
 * 计划步骤状态
 */
export type StepStatus = 'pending' | 'in_progress' | 'completed' | 'skipped' | 'failed';

/**
 * 计划步骤
 */
export interface PlanStep {
    /** 步骤 ID */
    id: number;
    /** 步骤描述 */
    description: string;
    /** 步骤状态 */
    status: StepStatus;
    /** 依赖的步骤 ID */
    dependsOn?: number[];
    /** 执行结果 */
    result?: string;
    /** 错误信息 */
    error?: string;
    /** 开始时间 */
    startedAt?: number;
    /** 完成时间 */
    completedAt?: number;
}

/**
 * 已知问题
 */
export interface KnownIssue {
    /** 问题 ID */
    id: number;
    /** 问题描述 */
    description: string;
    /** 严重程度 */
    severity: 'low' | 'medium' | 'high' | 'critical';
    /** 是否已解决 */
    resolved: boolean;
    /** 解决方案 */
    resolution?: string;
}

/**
 * 任务计划
 */
export interface TaskPlan {
    /** 任务 ID */
    taskId: string;
    /** 任务目标 */
    goal: string;
    /** 计划步骤 */
    steps: PlanStep[];
    /** 当前步骤索引 */
    currentStepIndex: number;
    /** 已知问题 */
    knownIssues: KnownIssue[];
    /** 上下文信息 */
    context: Record<string, unknown>;
    /** 创建时间 */
    createdAt: number;
    /** 更新时间 */
    updatedAt: number;
}

/**
 * ReAct 循环状态
 */
export interface ReActState {
    /** 当前阶段 */
    phase: 'perceive' | 'plan' | 'decide' | 'execute' | 'observe' | 'reflect';
    /** 循环次数 */
    iteration: number;
    /** 最大循环次数 */
    maxIterations: number;
    /** 感知结果 */
    perception?: string;
    /** 决策内容 */
    decision?: string;
    /** 执行动作 */
    action?: string;
    /** 观察结果 */
    observation?: string;
    /** 反思结论 */
    reflection?: ReflectionResult;
}

/**
 * 反思结果
 */
export interface ReflectionResult {
    /** 是否成功 */
    success: boolean;
    /** 原因分析 */
    reason: string;
    /** 下一步动作 */
    nextAction: 'continue' | 'retry' | 'replan' | 'escalate' | 'complete';
    /** 学习到的经验 */
    lessons?: string[];
}

/**
 * 计划分解结果
 */
export interface DecompositionResult {
    /** 分解后的步骤 */
    steps: PlanStep[];
    /** 预估总时间 */
    estimatedDuration?: number;
    /** 复杂度评估 */
    complexity: 'simple' | 'medium' | 'complex';
}
