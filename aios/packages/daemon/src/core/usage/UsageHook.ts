/**
 * UsageHook - 用量追踪 Hook
 * 从 AI 响应中提取 usage 信息并计算成本
 */

import { BaseHook } from '../hooks/BaseHook.js';
import { HookPriority, type TaskCompleteEvent } from '../hooks/types.js';
import { UsageRepository } from './UsageRepository.js';
import {
    DEFAULT_PRICING_TABLE,
    type AITier,
    type PricingTable,
    type UsageHookConfig,
} from './types.js';

/**
 * AI 响应中的 usage 信息
 */
interface AIUsageInfo {
    model?: string;
    usage?: {
        prompt_tokens?: number;
        completion_tokens?: number;
        total_tokens?: number;
        input_tokens?: number;
        output_tokens?: number;
    };
}

/**
 * 用量追踪 Hook
 */
export class UsageHook extends BaseHook {
    private repository: UsageRepository;
    private pricingTable: PricingTable;
    private enabled: boolean;

    constructor(
        repository: UsageRepository,
        config: UsageHookConfig = {}
    ) {
        super('UsageHook', {
            description: '追踪 AI 调用用量并计算成本',
            priority: HookPriority.LOW,
        });

        this.repository = repository;
        this.pricingTable = config.pricingTable ?? DEFAULT_PRICING_TABLE;
        this.enabled = config.enabled ?? true;
    }

    /**
     * 任务完成时记录用量
     */
    async onTaskComplete(event: TaskCompleteEvent): Promise<void> {
        if (!this.enabled) return;

        try {
            // 从任务结果中提取 usage 信息
            const usageInfo = this.extractUsageInfo(event);
            if (!usageInfo) return;

            const { model, inputTokens, outputTokens, tier } = usageInfo;
            const totalTokens = inputTokens + outputTokens;
            const cost = this.calculateCost(model, inputTokens, outputTokens);

            this.repository.create({
                sessionId: event.sessionId ?? 'unknown',
                taskId: event.taskId,
                model,
                tier,
                tokenInput: inputTokens,
                tokenOutput: outputTokens,
                tokenTotal: totalTokens,
                cost,
                duration: event.duration,
                createdAt: Date.now(),
                traceId: event.traceId,
            });
        } catch (error) {
            console.error('[UsageHook] Failed to record usage:', error);
        }
    }

    /**
     * 从任务事件中提取 usage 信息
     */
    private extractUsageInfo(event: TaskCompleteEvent): {
        model: string;
        inputTokens: number;
        outputTokens: number;
        tier: AITier;
    } | null {
        const result = event.result as unknown as {
            usage?: AIUsageInfo;
            model?: string;
            tier?: AITier;
        };

        if (!result) return null;

        // 尝试从不同格式中提取
        const model = result.model ?? 'unknown';
        let inputTokens = 0;
        let outputTokens = 0;

        // 获取 usage 对象（支持嵌套和直接访问）
        const usageData = (result.usage as AIUsageInfo)?.usage ?? result.usage;
        if (usageData && typeof usageData === 'object') {
            const usage = usageData as {
                prompt_tokens?: number;
                completion_tokens?: number;
                input_tokens?: number;
                output_tokens?: number;
            };
            // OpenAI 格式
            inputTokens = usage.prompt_tokens ?? usage.input_tokens ?? 0;
            outputTokens = usage.completion_tokens ?? usage.output_tokens ?? 0;
        }

        // 如果没有 usage 信息，跳过
        if (inputTokens === 0 && outputTokens === 0) return null;

        // 推断层级
        const tier = result.tier ?? this.inferTier(model);

        return { model, inputTokens, outputTokens, tier };
    }

    /**
     * 根据模型名推断层级
     */
    private inferTier(model: string): AITier {
        const modelLower = model.toLowerCase();

        // Fast 层
        if (
            modelLower.includes('mini') ||
            modelLower.includes('flash') ||
            modelLower.includes('haiku') ||
            modelLower.includes('3.5')
        ) {
            return 'fast';
        }

        // Vision 层（目前与 fast 重叠，但可以根据任务类型区分）
        if (modelLower.includes('vision')) {
            return 'vision';
        }

        // Smart 层
        if (
            modelLower.includes('sonnet') ||
            modelLower.includes('opus') ||
            modelLower.includes('pro') ||
            modelLower.includes('4o') ||
            modelLower.includes('gpt-4')
        ) {
            return 'smart';
        }

        return 'fast'; // 默认
    }

    /**
     * 计算成本（美元）
     */
    calculateCost(model: string, inputTokens: number, outputTokens: number): number {
        // 查找定价
        let pricing = this.pricingTable[model];

        // 尝试模糊匹配
        if (!pricing) {
            const modelLower = model.toLowerCase();
            for (const [key, value] of Object.entries(this.pricingTable)) {
                if (modelLower.includes(key.toLowerCase()) || key.toLowerCase().includes(modelLower)) {
                    pricing = value;
                    break;
                }
            }
        }

        // 默认定价（按 gpt-4o-mini 计算）
        if (!pricing) {
            pricing = { input: 0.15, output: 0.60 };
        }

        // 计算（定价是每百万 token）
        const inputCost = (inputTokens / 1_000_000) * pricing.input;
        const outputCost = (outputTokens / 1_000_000) * pricing.output;

        return inputCost + outputCost;
    }

    /**
     * 更新定价表
     */
    setPricingTable(table: PricingTable): void {
        this.pricingTable = table;
    }

    /**
     * 获取定价表
     */
    getPricingTable(): PricingTable {
        return { ...this.pricingTable };
    }

    /**
     * 设置启用状态
     */
    setEnabled(enabled: boolean): void {
        this.enabled = enabled;
    }

    /**
     * 获取统计
     */
    getStats(options?: { sessionId?: string; taskId?: string }) {
        return this.repository.getStats(options);
    }
}
