/**
 * UsageService - 用量服务
 * 提供用量查询和统计分析接口
 */

import { UsageRepository } from './UsageRepository.js';
import {
    DEFAULT_PRICING_TABLE,
    type UsageRecord,
    type UsageStats,
    type UsageQueryOptions,
    type PricingTable,
    type UsageServiceConfig,
    type AITier,
} from './types.js';

/**
 * 日期范围统计
 */
export interface DateRangeStats {
    /** 日期 (YYYY-MM-DD) */
    date: string;
    /** Token 数 */
    tokens: number;
    /** 成本 */
    cost: number;
    /** 调用次数 */
    calls: number;
}

/**
 * 用量服务
 */
export class UsageService {
    private repository: UsageRepository;
    private pricingTable: PricingTable;

    constructor(repository: UsageRepository, config: UsageServiceConfig = {}) {
        this.repository = repository;
        this.pricingTable = config.pricingTable ?? DEFAULT_PRICING_TABLE;
    }

    /**
     * 获取会话用量
     */
    getBySession(sessionId: string): UsageStats {
        return this.repository.getStats({ sessionId });
    }

    /**
     * 获取任务用量
     */
    getByTask(taskId: string): UsageRecord[] {
        return this.repository.query({ taskId });
    }

    /**
     * 获取总用量
     */
    getTotal(startTime?: number, endTime?: number): UsageStats {
        return this.repository.getStats({ startTime, endTime });
    }

    /**
     * 获取今日用量
     */
    getToday(): UsageStats {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        return this.repository.getStats({ startTime: today.getTime() });
    }

    /**
     * 获取本月用量
     */
    getThisMonth(): UsageStats {
        const firstDayOfMonth = new Date();
        firstDayOfMonth.setDate(1);
        firstDayOfMonth.setHours(0, 0, 0, 0);
        return this.repository.getStats({ startTime: firstDayOfMonth.getTime() });
    }

    /**
     * 获取日期范围内每日统计
     */
    getDailyStats(startTime: number, endTime: number): DateRangeStats[] {
        const records = this.repository.query({
            startTime,
            endTime,
            limit: 10000,
        });

        // 按日期聚合
        const dailyMap = new Map<string, { tokens: number; cost: number; calls: number }>();

        for (const record of records) {
            const date = new Date(record.createdAt).toISOString().split('T')[0];
            const existing = dailyMap.get(date) ?? { tokens: 0, cost: 0, calls: 0 };
            existing.tokens += record.tokenTotal;
            existing.cost += record.cost;
            existing.calls += 1;
            dailyMap.set(date, existing);
        }

        // 转换为数组并排序
        const result: DateRangeStats[] = [];
        for (const [date, stats] of dailyMap) {
            result.push({ date, ...stats });
        }
        result.sort((a, b) => a.date.localeCompare(b.date));

        return result;
    }

    /**
     * 获取成本预估
     */
    estimateCost(model: string, inputTokens: number, outputTokens: number): number {
        let pricing = this.pricingTable[model];

        if (!pricing) {
            // 默认使用 gpt-4o-mini 价格
            pricing = { input: 0.15, output: 0.60 };
        }

        return (inputTokens / 1_000_000) * pricing.input + (outputTokens / 1_000_000) * pricing.output;
    }

    /**
     * 获取层级成本占比
     */
    getTierCostBreakdown(startTime?: number, endTime?: number): {
        tier: AITier;
        cost: number;
        percentage: number;
    }[] {
        const stats = this.repository.getStats({ startTime, endTime });
        const totalCost = stats.totalCost || 1; // 避免除以零

        return (['fast', 'vision', 'smart'] as AITier[]).map(tier => ({
            tier,
            cost: stats.byTier[tier]?.cost ?? 0,
            percentage: ((stats.byTier[tier]?.cost ?? 0) / totalCost) * 100,
        }));
    }

    /**
     * 获取模型使用排行
     */
    getModelRanking(startTime?: number, endTime?: number, limit: number = 10): {
        model: string;
        tokens: number;
        cost: number;
        calls: number;
    }[] {
        const stats = this.repository.getStats({ startTime, endTime });

        const ranking = Object.entries(stats.byModel)
            .map(([model, data]) => ({ model, ...data }))
            .sort((a, b) => b.cost - a.cost)
            .slice(0, limit);

        return ranking;
    }

    /**
     * 清理过期记录
     */
    cleanup(): number {
        return this.repository.cleanup();
    }

    /**
     * 获取定价表
     */
    getPricingTable(): PricingTable {
        return { ...this.pricingTable };
    }

    /**
     * 更新定价表
     */
    setPricingTable(table: PricingTable): void {
        this.pricingTable = table;
    }
}
