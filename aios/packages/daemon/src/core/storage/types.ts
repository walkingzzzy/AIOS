/**
 * 存储系统类型定义
 */

/**
 * 会话状态
 */
export type SessionStatus = 'active' | 'paused' | 'completed' | 'expired';

/**
 * 会话记录
 */
export interface SessionRecord {
    /** 会话 ID */
    id: string;
    /** 会话标题 */
    title?: string;
    /** 创建时间 */
    createdAt: number;
    /** 更新时间 */
    updatedAt: number;
    /** 会话状态 */
    status: SessionStatus;
    /** 会话元数据 */
    metadata?: Record<string, unknown>;
}

/**
 * 任务状态
 */
export type StoredTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

/**
 * 任务记录
 */
export interface TaskRecord {
    /** 任务 ID */
    id: string;
    /** 所属会话 ID */
    sessionId: string;
    /** 任务类型 */
    type: string;
    /** 用户提示 */
    prompt: string;
    /** 任务状态 */
    status: StoredTaskStatus;
    /** 执行层级 */
    tier?: string;
    /** 创建时间 */
    createdAt: number;
    /** 开始时间 */
    startedAt?: number;
    /** 完成时间 */
    completedAt?: number;
    /** 执行时间 (ms) */
    executionTime?: number;
    /** 响应内容 */
    response?: string;
    /** 错误信息 */
    error?: string;
    /** 使用的模型 */
    model?: string;
    /** 任务元数据 */
    metadata?: Record<string, unknown>;
}

/**
 * 消息角色
 */
export type MessageRole = 'user' | 'assistant' | 'system';

/**
 * 消息记录
 */
export interface MessageRecord {
    /** 消息 ID */
    id: string;
    /** 所属会话 ID */
    sessionId: string;
    /** 关联任务 ID */
    taskId?: string;
    /** 消息角色 */
    role: MessageRole;
    /** 消息内容 */
    content: string;
    /** 创建时间 */
    createdAt: number;
    /** 消息元数据 (工具调用等) */
    metadata?: Record<string, unknown>;
}

/**
 * 工具执行记录
 */
export interface ToolExecutionRecord {
    /** 执行 ID */
    id: string;
    /** 所属任务 ID */
    taskId: string;
    /** 适配器 ID */
    adapterId: string;
    /** 能力 ID */
    capabilityId: string;
    /** 调用参数 */
    params: Record<string, unknown>;
    /** 是否成功 */
    success: boolean;
    /** 执行结果 */
    result?: unknown;
    /** 错误信息 */
    error?: string;
    /** 执行时间 (ms) */
    duration: number;
    /** 创建时间 */
    createdAt: number;
}

/**
 * 分页查询选项
 */
export interface PaginationOptions {
    /** 页码 (从 1 开始) */
    page?: number;
    /** 每页数量 */
    pageSize?: number;
    /** 排序字段 */
    orderBy?: string;
    /** 排序方向 */
    orderDir?: 'asc' | 'desc';
}

/**
 * 分页结果
 */
export interface PaginatedResult<T> {
    /** 数据列表 */
    data: T[];
    /** 总数 */
    total: number;
    /** 当前页 */
    page: number;
    /** 每页数量 */
    pageSize: number;
    /** 总页数 */
    totalPages: number;
}
