/**
 * Hook 系统类型定义
 */

import type { TaskResult, TaskAnalysis } from '../../types/orchestrator.js';

/**
 * Hook 优先级
 */
export enum HookPriority {
    /** 最高优先级，最先执行 */
    HIGHEST = 0,
    /** 高优先级 */
    HIGH = 25,
    /** 正常优先级 */
    NORMAL = 50,
    /** 低优先级 */
    LOW = 75,
    /** 最低优先级，最后执行 */
    LOWEST = 100,
}

/**
 * 任务状态
 */
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

/**
 * 任务进度信息
 */
export interface TaskProgress {
    /** 任务 ID */
    taskId: string;
    /** 当前步骤 */
    currentStep: number;
    /** 总步骤数 */
    totalSteps: number;
    /** 进度百分比 (0-100) */
    percentage: number;
    /** 当前步骤描述 */
    stepDescription?: string;
    /** 额外数据 */
    metadata?: Record<string, unknown>;
}

/**
 * 工具调用信息
 */
export interface ToolCallInfo {
    /** 工具 ID */
    toolId: string;
    /** 适配器 ID */
    adapterId: string;
    /** 能力 ID */
    capabilityId: string;
    /** 调用参数 */
    params: Record<string, unknown>;
    /** 调用时间戳 */
    timestamp: number;
    /** 会话 ID (用于审计) */
    sessionId?: string;
    /** 任务 ID (用于审计) */
    taskId?: string;
    /** 追踪 ID (用于链路追踪) */
    traceId?: string;
}

/**
 * 工具执行结果
 */
export interface ToolResultInfo extends ToolCallInfo {
    /** 是否成功 */
    success: boolean;
    /** 执行结果 */
    result?: unknown;
    /** 错误信息 */
    error?: Error;
    /** 执行耗时 (ms) */
    duration: number;
}

/**
 * 任务开始事件
 */
export interface TaskStartEvent {
    /** 任务 ID */
    taskId: string;
    /** 用户输入 */
    input: string;
    /** 任务分析结果 */
    analysis?: TaskAnalysis;
    /** 开始时间戳 */
    timestamp: number;
}

/**
 * 任务完成事件
 */
export interface TaskCompleteEvent {
    /** 任务 ID */
    taskId: string;
    /** 任务结果 */
    result: TaskResult;
    /** 完成时间戳 */
    timestamp: number;
    /** 总耗时 (ms) */
    duration: number;
    /** 会话 ID (用于用量统计) */
    sessionId?: string;
    /** 追踪 ID (用于链路追踪) */
    traceId?: string;
}

/**
 * 任务错误事件
 */
export interface TaskErrorEvent {
    /** 任务 ID */
    taskId: string;
    /** 错误对象 */
    error: Error;
    /** 错误时间戳 */
    timestamp: number;
    /** 是否可恢复 */
    recoverable: boolean;
}

/**
 * Hook 元数据
 */
export interface HookMetadata {
    /** Hook 名称 */
    name: string;
    /** Hook 描述 */
    description?: string;
    /** 优先级 */
    priority: HookPriority;
    /** 是否启用 */
    enabled: boolean;
}
