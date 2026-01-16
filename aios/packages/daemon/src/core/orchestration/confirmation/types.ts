/**
 * Confirmation 模块类型定义
 */

/**
 * 确认请求状态
 */
export type ConfirmationStatus = 'pending' | 'approved' | 'rejected' | 'timeout';

/**
 * 确认请求
 */
export interface ConfirmationRequest {
    /** 请求 ID */
    id: string;
    /** 任务 ID */
    taskId: string;
    /** 会话 ID */
    sessionId?: string;
    /** 操作描述 */
    action: string;
    /** 风险等级 */
    riskLevel: 'low' | 'medium' | 'high' | 'critical';
    /** 详细信息 */
    details: Record<string, unknown>;
    /** 状态 */
    status: ConfirmationStatus;
    /** 创建时间 */
    createdAt: number;
    /** 过期时间 */
    expiresAt: number;
    /** 用户回复 */
    response?: {
        approved: boolean;
        comment?: string;
        respondedAt: number;
    };
}

/**
 * 确认处理器回调
 */
export type ConfirmationHandler = (request: ConfirmationRequest) => Promise<boolean>;

/**
 * ConfirmationManager 配置
 */
export interface ConfirmationManagerConfig {
    /** 默认超时时间（毫秒） */
    timeout?: number;
    /** 是否自动批准低风险操作 */
    autoApproveLowRisk?: boolean;
    /** 是否启用 */
    enabled?: boolean;
}
