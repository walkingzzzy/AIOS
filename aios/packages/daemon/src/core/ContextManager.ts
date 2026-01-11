/**
 * 对话上下文管理器
 * 管理对话历史和上下文信息
 */

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

    constructor(maxHistory: number = 10) {
        this.maxHistory = maxHistory;
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
}
