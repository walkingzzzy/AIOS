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
    /** 任务 ID（用于审计/追踪/用量） */
    taskId?: string;
    /** 会话 ID（用于审计/用量聚合） */
    sessionId?: string;
    /** 中止信号（用于流式取消） */
    abortSignal?: AbortSignal;
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
    /** AI 用量信息（用于成本/审计） */
    usage?: unknown;
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

// ============================================================================
// 计划确认工作流类型 (Plan Confirmation Workflow Types)
// ============================================================================

/**
 * 计划状态
 * @description 用于跟踪执行计划的审批状态
 */
export type PlanStatus =
    | 'draft'              // 草案，尚未提交审批
    | 'pending_approval'   // 等待用户审批
    | 'approved'           // 用户已确认
    | 'rejected'           // 用户已拒绝
    | 'modified';          // 用户已修改

/**
 * 风险评估
 * @description 计划中识别的潜在风险
 */
export interface PlanRisk {
    /** 风险级别 */
    level: 'low' | 'medium' | 'high';
    /** 风险描述 */
    description: string;
    /** 缓解措施 */
    mitigation?: string;
}

/**
 * 计划草案
 * @description 比 ExecutionPlan 更详细，包含审批所需的额外信息
 */
export interface PlanDraft extends ExecutionPlan {
    /** 草案唯一 ID */
    draftId: string;
    /** 关联的任务 ID */
    taskId: string;
    /** 计划状态 */
    status: PlanStatus;
    /** 版本号 */
    version: number;
    /** 创建时间戳 */
    createdAt: number;
    /** 更新时间戳 */
    updatedAt: number;
    /** 计划摘要（用户友好的描述） */
    summary?: string;
    /** 方案说明（Markdown 格式的详细分析） */
    rationale?: string;
    /** 预估总执行时间 (ms) */
    estimatedDuration: number;
    /** 风险评估列表 */
    risks: PlanRisk[];
    /** 所需权限列表 */
    requiredPermissions: string[];
    /** 用户反馈（拒绝/修改时） */
    userFeedback?: string;
}

/**
 * 计划审批请求
 * @description 发送给前端的审批请求
 */
export interface PlanApprovalRequest {
    /** 任务 ID */
    taskId: string;
    /** 草案 ID */
    draftId: string;
    /** 计划详情 */
    plan: PlanDraft;
    /** 提示信息 */
    prompt: string;
    /** 超时时间 (ms)，超时后可自动处理 */
    timeout?: number;
}

/**
 * 计划审批响应
 * @description 用户审批后的响应
 */
export interface PlanApprovalResponse {
    /** 是否批准 */
    approved: boolean;
    /** 用户反馈 */
    feedback?: string;
    /** 用户修改的步骤（如果有修改） */
    modifiedSteps?: ExecutionStep[];
}

/**
 * 计划事件类型
 */
export type PlanEventType =
    | 'plan.created'
    | 'plan.approval_required'
    | 'plan.approved'
    | 'plan.rejected'
    | 'plan.modified'
    | 'plan.expired';

/**
 * 计划事件
 */
export interface PlanEvent {
    /** 事件类型 */
    type: PlanEventType;
    /** 任务 ID */
    taskId: string;
    /** 草案 ID */
    draftId: string;
    /** 时间戳 */
    timestamp: number;
    /** 事件数据 */
    data?: PlanDraft | PlanApprovalRequest | PlanApprovalResponse;
}

/** 重新导出内部工具定义类型 */
export type { InternalToolDefinition as ToolDefinition } from '@aios/shared';

