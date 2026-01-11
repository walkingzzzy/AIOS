/**
 * 三层 AI 协调系统类型定义
 */

import type { InternalToolDefinition } from '@aios/shared';

/** 任务类型 */
export enum TaskType {
    /** 简单任务：可直接匹配工具或 Fast 层处理 */
    Simple = 'simple',
    /** 视觉任务：需要屏幕理解 */
    Visual = 'visual',
    /** 复杂任务：需要任务规划 */
    Complex = 'complex',
}

/** 任务上下文 */
export interface TaskContext {
    /** 是否包含截图 */
    hasScreenshot?: boolean;
    /** 对话历史 */
    history?: Array<{ role: 'user' | 'assistant'; content: string }>;
}

/** 工具调用 */
export interface ToolCall {
    /** 工具/适配器 ID */
    tool: string;
    /** 动作/能力 ID */
    action: string;
    /** 参数 */
    params: Record<string, unknown>;
}

/** 任务分析结果 */
export interface TaskAnalysis {
    /** 任务类型 */
    taskType: TaskType;
    /** 直达工具调用（如果匹配到） */
    directToolCall?: ToolCall;
    /** 视觉提示（视觉任务时使用） */
    visionPrompt?: string;
    /** 是否需要任务规划 */
    requiresPlanning: boolean;
    /** 置信度 0-1 */
    confidence: number;
}

/** 任务执行结果 */
export interface TaskResult {
    /** 是否成功 */
    success: boolean;
    /** 响应内容 */
    response: string;
    /** 执行层级 */
    tier: 'direct' | 'fast' | 'vision' | 'smart';
    /** 执行时间 (ms) */
    executionTime: number;
    /** 使用的模型 */
    model?: string;
}

/** 执行计划 */
export interface ExecutionPlan {
    /** 任务目标 */
    goal: string;
    /** 执行步骤 */
    steps: ExecutionStep[];
}

/** 执行步骤 */
export interface ExecutionStep {
    /** 步骤 ID */
    id: number;
    /** 步骤描述 */
    description: string;
    /** 动作 (tool.action 或 vision.analyze) */
    action: string;
    /** 参数 */
    params: Record<string, unknown>;
    /** 是否需要视觉 */
    requiresVision: boolean;
    /** 依赖的步骤 ID */
    dependsOn: number[];
}

/** 步骤执行结果 */
export interface StepResult {
    /** 步骤 ID */
    stepId: number;
    /** 是否成功 */
    success: boolean;
    /** 输出数据 */
    output?: unknown;
    /** 错误信息 */
    error?: Error;
}

/** 失败处理决策 */
export type FailureDecision = 'retry' | 'alternative' | 'skip' | 'abort';

/** 重新导出内部工具定义类型 */
export type { InternalToolDefinition as ToolDefinition } from '@aios/shared';
