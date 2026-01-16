/**
 * 对话上下文管理器
 * 管理对话历史和上下文信息
 */

import type { PlanManager } from './planning/PlanManager.js';

export interface HistoryMessage {
    role: 'user' | 'assistant';
    content: string;
    timestamp: number;
}

/**
 * 对话上下文管理器
 */
export class ContextManager {
    private history: HistoryMessage[] = [];
    private maxHistory: number;
    private planManager?: PlanManager;

    constructor(maxHistory: number = 10, planManager?: PlanManager) {
        this.maxHistory = maxHistory;
        this.planManager = planManager;
    }

    /**
     * 添加消息到历史
     */
    addMessage(message: { role: 'user' | 'assistant'; content: string }): void {
        this.history.push({
            ...message,
            timestamp: Date.now(),
        });

        // 限制历史长度
        if (this.history.length > this.maxHistory * 2) {
            this.history = this.history.slice(-this.maxHistory);
        }
    }

    /**
     * 获取最近的历史消息
     */
    getRecentHistory(count: number = 5): HistoryMessage[] {
        return this.history.slice(-count);
    }

    /**
     * 获取格式化的消息列表（用于 AI API）
     */
    getMessagesForAI(count: number = 5): Array<{ role: 'user' | 'assistant'; content: string }> {
        return this.getRecentHistory(count).map(({ role, content }) => ({ role, content }));
    }

    /**
     * 清空历史
     */
    clear(): void {
        this.history = [];
    }

    /**
     * 获取历史长度
     */
    get length(): number {
        return this.history.length;
    }

    /**
     * 智能压缩上下文
     * 当 Token 超限时，保留系统提示词 + PLAN 摘要 + 最近 N 条消息
     */
    compress(taskId?: string, keepRecent: number = 3): void {
        if (this.history.length <= keepRecent) return;

        // 保留最近消息
        const recentMessages = this.history.slice(-keepRecent);

        // 如果有 PlanManager，生成计划摘要作为上下文
        let planContext = '';
        if (this.planManager && taskId) {
            planContext = this.planManager.getPlanSummary(taskId);
        }

        // 创建压缩消息
        const compressedMessage: HistoryMessage = {
            role: 'assistant',
            content: `[Context compressed. ${this.history.length - keepRecent} messages summarized]\n` +
                (planContext ? `Current Plan:\n${planContext}` : ''),
            timestamp: Date.now(),
        };

        this.history = [compressedMessage, ...recentMessages];
        console.log(`[ContextManager] Compressed to ${this.history.length} messages`);
    }

    /**
     * 检查是否需要压缩
     */
    needsCompression(tokenLimit: number = 4000): boolean {
        // 简单估算：每4个字符约1个token
        const estimatedTokens = this.history.reduce((sum, m) => sum + m.content.length / 4, 0);
        return estimatedTokens > tokenLimit * 0.8;
    }
}
