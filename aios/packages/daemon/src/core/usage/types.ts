/**
 * Usage 模块类型定义
 */

/**
 * AI 层级
 */
export type AITier = 'fast' | 'vision' | 'smart';

/**
 * 用量记录
 */
export interface UsageRecord {
    /** 记录 ID */
    id: string;
    /** 会话 ID */
    sessionId: string;
    /** 任务 ID */
    taskId: string;
    /** 模型名称 */
    model: string;
    /** AI 层级 */
    tier: AITier;
    /** 输入 Token 数 */
    tokenInput: number;
    /** 输出 Token 数 */
    tokenOutput: number;
    /** 总 Token 数 */
    tokenTotal: number;
    /** 成本（美元） */
    cost: number;
    /** 执行时长（毫秒） */
    duration: number;
    /** 创建时间戳 */
    createdAt: number;
    /** 追踪 ID */
    traceId?: string;
}

/**
 * 用量统计
 */
export interface UsageStats {
    /** 总 Token 数 */
    totalTokens: number;
    /** 总成本 */
    totalCost: number;
    /** 总调用次数 */
    totalCalls: number;
    /** 平均执行时长 */
    avgDuration: number;
    /** 按模型统计 */
    byModel: Record<string, {
        tokens: number;
        cost: number;
        calls: number;
    }>;
    /** 按层级统计 */
    byTier: Record<AITier, {
        tokens: number;
        cost: number;
        calls: number;
    }>;
}

/**
 * 用量查询选项
 */
export interface UsageQueryOptions {
    /** 会话 ID */
    sessionId?: string;
    /** 任务 ID */
    taskId?: string;
    /** 模型筛选 */
    model?: string;
    /** 层级筛选 */
    tier?: AITier;
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
 * 模型定价（每百万 Token，美元）
 */
export interface ModelPricing {
    /** 输入价格 */
    input: number;
    /** 输出价格 */
    output: number;
}

/**
 * 模型定价表
 */
export type PricingTable = Record<string, ModelPricing>;

/**
 * 默认模型定价表（每百万 Token，美元）
 */
export const DEFAULT_PRICING_TABLE: PricingTable = {
    // OpenAI
    'gpt-4o': { input: 2.50, output: 10.00 },
    'gpt-4o-mini': { input: 0.15, output: 0.60 },
    'gpt-4-turbo': { input: 10.00, output: 30.00 },
    'gpt-4': { input: 30.00, output: 60.00 },
    'gpt-3.5-turbo': { input: 0.50, output: 1.50 },

    // Claude
    'claude-3-5-sonnet-20241022': { input: 3.00, output: 15.00 },
    'claude-3-5-haiku-20241022': { input: 0.80, output: 4.00 },
    'claude-3-opus-20240229': { input: 15.00, output: 75.00 },
    'claude-3-sonnet-20240229': { input: 3.00, output: 15.00 },
    'claude-3-haiku-20240307': { input: 0.25, output: 1.25 },

    // Google
    'gemini-2.0-flash-exp': { input: 0.075, output: 0.30 },
    'gemini-1.5-flash': { input: 0.075, output: 0.30 },
    'gemini-1.5-flash-8b': { input: 0.0375, output: 0.15 },
    'gemini-1.5-pro': { input: 1.25, output: 5.00 },

    // DeepSeek
    'deepseek-chat': { input: 0.14, output: 0.28 },
    'deepseek-reasoner': { input: 0.55, output: 2.19 },
};

/**
 * 层级默认模型映射
 */
export const TIER_DEFAULT_MODELS: Record<AITier, string> = {
    fast: 'gpt-4o-mini',
    vision: 'gemini-2.0-flash-exp',
    smart: 'claude-3-5-sonnet-20241022',
};

/**
 * UsageRepository 配置
 */
export interface UsageRepositoryConfig {
    /** 数据库路径 */
    dbPath?: string;
    /** 最大保留记录数 */
    maxRecords?: number;
    /** 自动清理天数 */
    retentionDays?: number;
}

/**
 * UsageHook 配置
 */
export interface UsageHookConfig {
    /** 是否启用 */
    enabled?: boolean;
    /** 定价表 */
    pricingTable?: PricingTable;
}

/**
 * UsageService 配置
 */
export interface UsageServiceConfig {
    /** 定价表 */
    pricingTable?: PricingTable;
}
