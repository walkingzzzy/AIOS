/**
 * 任务调度系统类型定义
 */

/**
 * 任务优先级
 */
export enum TaskPriority {
    /** 最高优先级 - 用户交互任务 */
    CRITICAL = 0,
    /** 高优先级 */
    HIGH = 1,
    /** 正常优先级 */
    NORMAL = 2,
    /** 低优先级 - 后台任务 */
    LOW = 3,
    /** 最低优先级 */
    BACKGROUND = 4,
}

/**
 * 任务状态
 */
export enum TaskStatus {
    /** 等待执行 */
    PENDING = 'pending',
    /** 正在执行 */
    RUNNING = 'running',
    /** 执行成功 */
    COMPLETED = 'completed',
    /** 执行失败 */
    FAILED = 'failed',
    /** 已取消 */
    CANCELLED = 'cancelled',
    /** 超时 */
    TIMEOUT = 'timeout',
}

/**
 * 任务类型
 */
export type TaskType = 'simple' | 'visual' | 'complex' | 'background';

/**
 * 任务定义
 */
export interface Task<TResult = unknown> {
    /** 任务 ID */
    id: string;
    /** 任务类型 */
    type: TaskType;
    /** 优先级 */
    priority: TaskPriority;
    /** 任务状态 */
    status: TaskStatus;
    /** 用户输入/提示 */
    prompt: string;
    /** 任务上下文 */
    context?: Record<string, unknown>;
    /** 创建时间 */
    createdAt: number;
    /** 开始时间 */
    startedAt?: number;
    /** 完成时间 */
    completedAt?: number;
    /** 执行结果 */
    result?: TResult;
    /** 错误信息 */
    error?: Error;
    /** 超时时间 (ms) */
    timeout?: number;
    /** 重试次数 */
    retryCount?: number;
    /** 最大重试次数 */
    maxRetries?: number;
    /** 任务元数据 */
    metadata?: Record<string, unknown>;
}

/**
 * 任务提交选项
 */
export interface TaskSubmitOptions {
    /** 指定任务 ID（可选，用于与外部存储对齐） */
    id?: string;
    /** 优先级 */
    priority?: TaskPriority;
    /** 任务类型 */
    type?: TaskType;
    /** 超时时间 (ms) */
    timeout?: number;
    /** 最大重试次数 */
    maxRetries?: number;
    /** 任务上下文 */
    context?: Record<string, unknown>;
    /** 任务元数据 */
    metadata?: Record<string, unknown>;
}

/**
 * 任务执行器函数
 */
export type TaskExecutor<TResult = unknown> = (task: Task<TResult>) => Promise<TResult>;

/**
 * 队列统计信息
 */
export interface QueueStats {
    /** 队列中等待的任务数 */
    pending: number;
    /** 正在执行的任务数 */
    running: number;
    /** 已完成的任务数 */
    completed: number;
    /** 失败的任务数 */
    failed: number;
    /** 总任务数 */
    total: number;
    /** 队列是否暂停 */
    isPaused: boolean;
    /** 并发限制 */
    concurrency: number;
}

/**
 * 调度器事件
 */
export interface SchedulerEvents {
    /** 任务添加到队列 */
    'task:queued': (task: Task) => void;
    /** 任务开始执行 */
    'task:started': (task: Task) => void;
    /** 任务执行完成 */
    'task:completed': (task: Task) => void;
    /** 任务执行失败 */
    'task:failed': (task: Task, error: Error) => void;
    /** 任务被取消 */
    'task:cancelled': (task: Task) => void;
    /** 队列空闲 */
    'queue:idle': () => void;
    /** 队列活跃（有新任务） */
    'queue:active': () => void;
}
