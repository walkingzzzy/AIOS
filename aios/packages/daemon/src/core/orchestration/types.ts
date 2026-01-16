/**
 * Orchestrator-Worker 模式类型定义
 */

/**
 * Worker 状态
 */
export type WorkerStatus = 'idle' | 'busy' | 'error' | 'offline';

/**
 * 子任务定义
 */
export interface SubTask {
    /** 子任务 ID */
    id: string;
    /** 子任务描述 */
    description: string;
    /** 分配的 Worker ID */
    workerId?: string;
    /** 任务状态 */
    status: 'pending' | 'assigned' | 'running' | 'completed' | 'failed';
    /** 依赖的子任务 ID */
    dependencies?: string[];
    /** 任务参数 */
    params: Record<string, unknown>;
    /** 执行结果 */
    result?: unknown;
    /** 错误信息 */
    error?: string;
    /** 预估时间 (ms) */
    estimatedTime?: number;
    /** 实际用时 (ms) */
    actualTime?: number;
}

/**
 * Worker 定义
 */
export interface Worker {
    /** Worker ID */
    id: string;
    /** Worker 名称 */
    name: string;
    /** Worker 能力标签 */
    capabilities: string[];
    /** 当前状态 */
    status: WorkerStatus;
    /** 当前任务 ID */
    currentTaskId?: string;
    /** 已完成任务数 */
    completedTasks: number;
    /** 平均执行时间 */
    avgExecutionTime: number;
}

/**
 * 任务分解结果
 */
export interface TaskDecomposition {
    /** 原始任务描述 */
    originalTask: string;
    /** 分解后的子任务 */
    subTasks: SubTask[];
    /** 执行策略 */
    strategy: 'sequential' | 'parallel' | 'mixed';
    /** 预估总时间 */
    estimatedTotalTime: number;
}

/**
 * 合并策略
 */
export type MergeStrategy = 'concat' | 'summarize' | 'structured' | 'custom';

/**
 * 结果合并配置
 */
export interface MergeConfig {
    /** 合并策略 */
    strategy: MergeStrategy;
    /** 是否保留原始结果 */
    keepOriginal: boolean;
    /** 自定义合并函数 */
    customMerger?: (results: unknown[]) => unknown;
}

/**
 * Orchestrator 配置
 */
export interface OrchestratorConfig {
    /** 最大并行 Worker 数 */
    maxParallelWorkers: number;
    /** Worker 超时时间 (ms) */
    workerTimeout: number;
    /** 是否启用自动重试 */
    enableRetry: boolean;
    /** 结果合并配置 */
    mergeConfig: MergeConfig;
}

/**
 * 安全审计事件
 */
export interface AuditEvent {
    /** 事件 ID */
    id: string;
    /** 时间戳 */
    timestamp: number;
    /** 事件类型 */
    type: 'tool_call' | 'data_access' | 'system_change' | 'security_alert';
    /** 风险级别 */
    riskLevel: 'low' | 'medium' | 'high' | 'critical';
    /** 操作者 */
    actor: string;
    /** 目标资源 */
    resource: string;
    /** 操作详情 */
    details: Record<string, unknown>;
    /** 是否需要确认 */
    requiresConfirmation: boolean;
}

/**
 * 提示注入检测结果
 */
export interface InjectionCheckResult {
    /** 是否检测到注入 */
    detected: boolean;
    /** 风险级别 */
    riskLevel: 'none' | 'low' | 'medium' | 'high';
    /** 检测到的模式 */
    patterns: string[];
    /** 建议 */
    recommendation: string;
}
