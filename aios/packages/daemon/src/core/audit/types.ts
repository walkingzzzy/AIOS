/**
 * Audit 模块类型定义
 */

/**
 * 工具追踪状态
 */
export type ToolTraceStatus = 'pending' | 'completed' | 'failed';

/**
 * 工具追踪记录
 */
export interface ToolTrace {
    /** 工具使用 ID（唯一标识，用于去重） */
    toolUseId: string;
    /** 会话 ID */
    sessionId: string;
    /** 任务 ID */
    taskId: string;
    /** 适配器 ID */
    adapterId: string;
    /** 能力 ID */
    capabilityId: string;
    /** 输入参数 */
    input: Record<string, unknown>;
    /** 输出结果 */
    output?: unknown;
    /** 错误信息 */
    error?: string;
    /** 状态 */
    status: ToolTraceStatus;
    /** 开始时间戳 */
    startedAt: number;
    /** 完成时间戳 */
    completedAt?: number;
    /** 执行时长（毫秒） */
    duration?: number;
    /** 追踪 ID */
    traceId?: string;
}

/**
 * 工具追踪查询选项
 */
export interface ToolTraceQueryOptions {
    /** 会话 ID */
    sessionId?: string;
    /** 任务 ID */
    taskId?: string;
    /** 适配器 ID */
    adapterId?: string;
    /** 状态筛选 */
    status?: ToolTraceStatus;
    /** 开始时间 */
    startTime?: number;
    /** 结束时间 */
    endTime?: number;
    /** 分页偏移 */
    offset?: number;
    /** 分页大小 */
    limit?: number;
}

/**
 * 工具追踪统计
 */
export interface ToolTraceStats {
    /** 总调用次数 */
    totalCalls: number;
    /** 成功次数 */
    successCount: number;
    /** 失败次数 */
    failureCount: number;
    /** 待处理次数 */
    pendingCount: number;
    /** 平均执行时长（毫秒） */
    avgDuration: number;
    /** 按适配器统计 */
    byAdapter: Record<string, {
        calls: number;
        successRate: number;
        avgDuration: number;
    }>;
}

/**
 * ToolTraceRepository 配置
 */
export interface ToolTraceRepositoryConfig {
    /** 数据库路径 */
    dbPath?: string;
    /** 最大保留记录数 */
    maxRecords?: number;
    /** 自动清理天数 */
    retentionDays?: number;
}

/**
 * ToolTraceHook 配置
 */
export interface ToolTraceHookConfig {
    /** 是否启用 */
    enabled?: boolean;
    /** 是否记录输入参数 */
    logInput?: boolean;
    /** 是否记录输出结果 */
    logOutput?: boolean;
    /** 输入参数最大长度 */
    maxInputLength?: number;
    /** 输出结果最大长度 */
    maxOutputLength?: number;
}
