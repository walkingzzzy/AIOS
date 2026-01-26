/**
 * LLMCostTrackingHook - LLM 成本追踪 Hook
 * 追踪 LLM 调用的 Token 使用量和估算成本
 */

import { BaseHook } from './BaseHook.js';
import { HookPriority } from './types.js';
import type {
    LLMResponseEvent,
} from './types.js';

/** 模型价格配置 (每 1000 tokens 的价格，单位：美元) */
export interface ModelPricing {
    /** 输入 Token 价格 */
    inputPrice: number;
    /** 输出 Token 价格 */
    outputPrice: number;
}

/** 成本记录 */
export interface CostRecord {
    requestId: string;
    taskId?: string;
    model: string;
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    inputCost: number;
    outputCost: number;
    totalCost: number;
    timestamp: number;
}

/** 成本汇总 */
export interface CostSummary {
    totalRequests: number;
    totalPromptTokens: number;
    totalCompletionTokens: number;
    totalTokens: number;
    totalCost: number;
    costByModel: Map<string, {
        requests: number;
        promptTokens: number;
        completionTokens: number;
        cost: number;
    }>;
    dailyCost: Map<string, number>;
}

/** 默认模型价格 (GPT-4 级别估算) */
const DEFAULT_PRICING: Record<string, ModelPricing> = {
    // OpenAI
    'gpt-4': { inputPrice: 0.03, outputPrice: 0.06 },
    'gpt-4-turbo': { inputPrice: 0.01, outputPrice: 0.03 },
    'gpt-4o': { inputPrice: 0.005, outputPrice: 0.015 },
    'gpt-4o-mini': { inputPrice: 0.00015, outputPrice: 0.0006 },
    'gpt-3.5-turbo': { inputPrice: 0.0005, outputPrice: 0.0015 },

    // Claude
    'claude-3-opus': { inputPrice: 0.015, outputPrice: 0.075 },
    'claude-3-sonnet': { inputPrice: 0.003, outputPrice: 0.015 },
    'claude-3-haiku': { inputPrice: 0.00025, outputPrice: 0.00125 },

    // Gemini
    'gemini-pro': { inputPrice: 0.00025, outputPrice: 0.0005 },
    'gemini-1.5-pro': { inputPrice: 0.00125, outputPrice: 0.005 },
    'gemini-1.5-flash': { inputPrice: 0.000075, outputPrice: 0.0003 },

    // DeepSeek
    'deepseek-chat': { inputPrice: 0.00014, outputPrice: 0.00028 },
    'deepseek-coder': { inputPrice: 0.00014, outputPrice: 0.00028 },

    // 默认
    'default': { inputPrice: 0.001, outputPrice: 0.002 },
};

/** 成本追踪配置 */
export interface LLMCostTrackingConfig {
    /** 自定义模型价格 */
    pricing?: Record<string, ModelPricing>;
    /** 成本预警阈值 (美元) */
    alertThreshold?: number;
    /** 预警回调 */
    onAlert?: (summary: CostSummary) => void;
    /** 最大记录数 */
    maxRecords?: number;
}

/**
 * LLM 成本追踪 Hook
 */
export class LLMCostTrackingHook extends BaseHook {
    private records: CostRecord[] = [];
    private pricing: Record<string, ModelPricing>;
    private alertThreshold: number;
    private onAlert?: (summary: CostSummary) => void;
    private maxRecords: number;
    private lastAlertTime: number = 0;

    constructor(config: LLMCostTrackingConfig = {}) {
        super('llm-cost-tracking', {
            description: '追踪 LLM 调用的 Token 使用量和成本',
            priority: HookPriority.LOW,
        });

        this.pricing = { ...DEFAULT_PRICING, ...config.pricing };
        this.alertThreshold = config.alertThreshold ?? 10; // 默认 $10 预警
        this.onAlert = config.onAlert;
        this.maxRecords = config.maxRecords ?? 10000;
    }

    /**
     * LLM 响应完成时记录成本
     */
    async onLLMResponse(event: LLMResponseEvent): Promise<void> {
        if (!event.usage) return;

        const pricing = this.getPricing(event.model);
        const inputCost = (event.usage.promptTokens / 1000) * pricing.inputPrice;
        const outputCost = (event.usage.completionTokens / 1000) * pricing.outputPrice;

        const record: CostRecord = {
            requestId: event.requestId,
            taskId: event.taskId,
            model: event.model,
            promptTokens: event.usage.promptTokens,
            completionTokens: event.usage.completionTokens,
            totalTokens: event.usage.totalTokens,
            inputCost,
            outputCost,
            totalCost: inputCost + outputCost,
            timestamp: event.timestamp,
        };

        this.records.push(record);
        this.pruneRecords();

        // 检查成本预警
        this.checkAlert();
    }

    /**
     * 获取成本汇总
     */
    getSummary(): CostSummary {
        const costByModel = new Map<string, {
            requests: number;
            promptTokens: number;
            completionTokens: number;
            cost: number;
        }>();

        const dailyCost = new Map<string, number>();

        let totalPromptTokens = 0;
        let totalCompletionTokens = 0;
        let totalCost = 0;

        for (const record of this.records) {
            // 按模型统计
            const modelStats = costByModel.get(record.model) ?? {
                requests: 0,
                promptTokens: 0,
                completionTokens: 0,
                cost: 0,
            };
            modelStats.requests++;
            modelStats.promptTokens += record.promptTokens;
            modelStats.completionTokens += record.completionTokens;
            modelStats.cost += record.totalCost;
            costByModel.set(record.model, modelStats);

            // 按日期统计
            const date = new Date(record.timestamp).toISOString().split('T')[0];
            dailyCost.set(date, (dailyCost.get(date) ?? 0) + record.totalCost);

            // 总计
            totalPromptTokens += record.promptTokens;
            totalCompletionTokens += record.completionTokens;
            totalCost += record.totalCost;
        }

        return {
            totalRequests: this.records.length,
            totalPromptTokens,
            totalCompletionTokens,
            totalTokens: totalPromptTokens + totalCompletionTokens,
            totalCost,
            costByModel,
            dailyCost,
        };
    }

    /**
     * 获取今日成本
     */
    getTodayCost(): number {
        const today = new Date().toISOString().split('T')[0];
        return this.records
            .filter(r => new Date(r.timestamp).toISOString().split('T')[0] === today)
            .reduce((sum, r) => sum + r.totalCost, 0);
    }

    /**
     * 获取本月成本
     */
    getMonthCost(): number {
        const now = new Date();
        const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
        return this.records
            .filter(r => r.timestamp >= monthStart)
            .reduce((sum, r) => sum + r.totalCost, 0);
    }

    /**
     * 获取按任务分组的成本
     */
    getCostByTask(): Map<string, number> {
        const result = new Map<string, number>();
        for (const record of this.records) {
            if (record.taskId) {
                result.set(record.taskId, (result.get(record.taskId) ?? 0) + record.totalCost);
            }
        }
        return result;
    }

    /**
     * 获取最近 N 条记录
     */
    getRecentRecords(count: number = 50): CostRecord[] {
        return this.records.slice(-count);
    }

    /**
     * 获取所有记录
     */
    getAllRecords(): CostRecord[] {
        return [...this.records];
    }

    /**
     * 设置成本预警阈值
     */
    setAlertThreshold(threshold: number): void {
        this.alertThreshold = threshold;
    }

    /**
     * 更新模型价格
     */
    updatePricing(model: string, pricing: ModelPricing): void {
        this.pricing[model] = pricing;
    }

    /**
     * 重置统计
     */
    reset(): void {
        this.records = [];
        this.lastAlertTime = 0;
    }

    /**
     * 导出为 JSON
     */
    export(): string {
        return JSON.stringify({
            summary: {
                ...this.getSummary(),
                costByModel: Object.fromEntries(this.getSummary().costByModel),
                dailyCost: Object.fromEntries(this.getSummary().dailyCost),
            },
            records: this.records,
        }, null, 2);
    }

    /**
     * 格式化成本显示
     */
    formatCost(cost: number): string {
        if (cost < 0.01) {
            return `$${(cost * 100).toFixed(4)}¢`;
        }
        return `$${cost.toFixed(4)}`;
    }

    private getPricing(model: string): ModelPricing {
        // 精确匹配
        if (this.pricing[model]) {
            return this.pricing[model];
        }

        // 模糊匹配
        const modelLower = model.toLowerCase();
        for (const [key, pricing] of Object.entries(this.pricing)) {
            if (modelLower.includes(key.toLowerCase())) {
                return pricing;
            }
        }

        // 返回默认
        return this.pricing['default'];
    }

    private pruneRecords(): void {
        if (this.records.length > this.maxRecords) {
            this.records = this.records.slice(-this.maxRecords);
        }
    }

    private checkAlert(): void {
        const totalCost = this.getSummary().totalCost;
        const now = Date.now();

        // 每小时最多预警一次
        if (totalCost >= this.alertThreshold && now - this.lastAlertTime > 3600000) {
            this.lastAlertTime = now;
            console.warn(`[LLMCostTracking] ⚠️ 成本预警: 总成本已达 $${totalCost.toFixed(2)}, 超过阈值 $${this.alertThreshold}`);

            if (this.onAlert) {
                this.onAlert(this.getSummary());
            }
        }
    }
}
