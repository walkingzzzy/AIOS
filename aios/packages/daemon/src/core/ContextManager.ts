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
    private histories: Map<string, HistoryMessage[]> = new Map();
    private maxHistory: number;
    private planManager?: PlanManager;
    private defaultSessionId = 'default';

    constructor(maxHistory: number = 10, planManager?: PlanManager) {
        this.maxHistory = maxHistory;
        this.planManager = planManager;
    }

    /**
     * 添加消息到历史
     */
    addMessage(message: { role: 'user' | 'assistant'; content: string }, sessionId?: string): void {
        const key = this.getSessionKey(sessionId);
        const history = this.getHistory(key);

        history.push({
            ...message,
            timestamp: Date.now(),
        });

        // 限制历史长度
        if (history.length > this.maxHistory * 2) {
            this.histories.set(key, history.slice(-this.maxHistory));
        }
    }

    /**
     * 获取最近的历史消息
     */
    getRecentHistory(count: number = 5, sessionId?: string): HistoryMessage[] {
        return this.getHistory(this.getSessionKey(sessionId)).slice(-count);
    }

    /**
     * 获取格式化的消息列表（用于 AI API）
     */
    getMessagesForAI(count: number = 5, sessionId?: string): Array<{ role: 'user' | 'assistant'; content: string }> {
        return this.getRecentHistory(count, sessionId).map(({ role, content }) => ({ role, content }));
    }

    /**
     * 清空历史
     */
    clear(sessionId?: string): void {
        if (sessionId) {
            this.histories.delete(this.getSessionKey(sessionId));
            return;
        }
        this.histories.clear();
    }

    /**
     * 获取历史长度
     */
    get length(): number {
        let total = 0;
        for (const history of this.histories.values()) {
            total += history.length;
        }
        return total;
    }

    /**
     * 智能压缩上下文
     * 当 Token 超限时，保留系统提示词 + PLAN 摘要 + 最近 N 条消息
     */
    compress(taskId?: string, keepRecent: number = 3, sessionId?: string): void {
        const key = this.getSessionKey(sessionId);
        const history = this.getHistory(key);
        if (history.length <= keepRecent) return;

        // 保留最近消息
        const recentMessages = history.slice(-keepRecent);

        // 如果有 PlanManager，生成计划摘要作为上下文
        let planContext = '';
        if (this.planManager && taskId) {
            planContext = this.planManager.getPlanSummary(taskId);
        }

        // 创建压缩消息
        const compressedMessage: HistoryMessage = {
            role: 'assistant',
            content: `[Context compressed. ${history.length - keepRecent} messages summarized]\n` +
                (planContext ? `Current Plan:\n${planContext}` : ''),
            timestamp: Date.now(),
        };

        this.histories.set(key, [compressedMessage, ...recentMessages]);
        console.log(`[ContextManager] Compressed to ${this.histories.get(key)?.length ?? 0} messages`);
    }

    /**
     * 检查是否需要压缩
     */
    needsCompression(tokenLimit: number = 4000, sessionId?: string): boolean {
        // 简单估算：每4个字符约1个token
        const history = this.getHistory(this.getSessionKey(sessionId));
        const estimatedTokens = history.reduce((sum, m) => sum + m.content.length / 4, 0);
        return estimatedTokens > tokenLimit * 0.8;
    }

    private getSessionKey(sessionId?: string): string {
        return sessionId ?? this.defaultSessionId;
    }

    private getHistory(key: string): HistoryMessage[] {
        const existing = this.histories.get(key);
        if (existing) {
            return existing;
        }
        const fresh: HistoryMessage[] = [];
        this.histories.set(key, fresh);
        return fresh;
    }
}
