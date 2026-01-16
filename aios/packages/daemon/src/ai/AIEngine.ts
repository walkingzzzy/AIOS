/**
 * AI 引擎抽象基类
 */

import type {
    IAIEngine,
    AIProvider,
    Message,
    ChatOptions,
    ChatResponse,
    ToolDefinition,
    ToolCallResponse,
} from '@aios/shared';

export abstract class BaseAIEngine implements IAIEngine {
    abstract readonly id: string;
    abstract readonly name: string;
    abstract readonly provider: AIProvider;
    abstract readonly model: string;

    /** 基础聊天 */
    abstract chat(messages: Message[], options?: ChatOptions): Promise<ChatResponse>;

    /** 带工具调用的聊天 */
    abstract chatWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: ChatOptions
    ): Promise<ToolCallResponse>;

    /** 是否支持视觉能力 */
    supportsVision(): boolean {
        return false;
    }

    /** 是否支持工具调用 */
    supportsToolCalling(): boolean {
        return true;
    }

    /** 获取最大 token 数 */
    getMaxTokens(): number {
        return 4096;
    }

    /** 获取引擎配置信息 */
    abstract getConfigInfo(): {
        model: string;
        apiUrl: string;
        isConfigured: boolean;
    };

    /** 生成响应 ID */
    protected generateId(): string {
        return `aios-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    }
}
