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
    StreamChunk,
    StreamOptions,
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

    /** 流式聊天 */
    async *chatStream(
        messages: Message[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown> {
        // 默认实现：使用非流式方法模拟
        const response = await this.chat(messages, options);
        yield {
            content: response.content,
            finishReason: response.finishReason,
            usage: response.usage ? {
                promptTokens: response.usage.promptTokens,
                completionTokens: response.usage.completionTokens,
                totalTokens: response.usage.totalTokens,
            } : undefined,
        };
    }

    /** 流式带工具调用的聊天 */
    async *chatStreamWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown> {
        // 默认实现：使用非流式方法模拟
        const response = await this.chatWithTools(messages, tools, options);
        yield {
            content: response.content,
            toolCalls: response.toolCalls?.map((tc, index) => ({
                index,
                id: tc.id,
                type: tc.type,
                function: {
                    name: tc.function.name,
                    arguments: tc.function.arguments,
                },
            })),
            finishReason: response.finishReason,
            usage: response.usage ? {
                promptTokens: response.usage.promptTokens,
                completionTokens: response.usage.completionTokens,
                totalTokens: response.usage.totalTokens,
            } : undefined,
        };
    }

    /** 是否支持视觉能力 */
    supportsVision(): boolean {
        return false;
    }

    /** 是否支持工具调用 */
    supportsToolCalling(): boolean {
        return true;
    }

    /** 是否支持流式响应 */
    supportsStreaming(): boolean {
        return false; // 子类覆盖为 true 以启用真正的流式
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

