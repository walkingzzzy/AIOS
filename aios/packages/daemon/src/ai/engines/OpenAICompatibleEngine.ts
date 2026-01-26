/**
 * OpenAI 兼容引擎
 * 支持: OpenAI, DeepSeek, Qwen, Mistral, Groq, Together, OpenRouter, xAI
 */

import OpenAI from 'openai';
import { BaseAIEngine } from '../AIEngine.js';
import { normalizeBase64Image, toDataUrl } from '../utils/images.js';
import type {
    AIProvider,
    Message,
    ChatOptions,
    ChatResponse,
    ToolDefinition,
    ToolCallResponse,
    StreamChunk,
    StreamOptions,
    ToolCallDelta,
} from '@aios/shared';

export interface OpenAICompatibleConfig {
    provider: AIProvider;
    model: string;
    apiKey: string;
    baseURL?: string;
}

export class OpenAICompatibleEngine extends BaseAIEngine {
    readonly id: string;
    readonly name: string;
    readonly provider: AIProvider;
    readonly model: string;

    private client: OpenAI;
    private baseURL: string;
    private apiKey: string;

    constructor(config: OpenAICompatibleConfig) {
        super();
        this.provider = config.provider;
        this.model = config.model;
        this.id = `${config.provider}/${config.model}`;
        this.name = `${config.provider} - ${config.model}`;

        // 根据提供商获取默认端点
        const defaultEndpoints: Record<string, string> = {
            openai: 'https://api.openai.com/v1',
            deepseek: 'https://api.deepseek.com/v1',
            qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            mistral: 'https://api.mistral.ai/v1',
            groq: 'https://api.groq.com/openai/v1',
            together: 'https://api.together.xyz/v1',
            openrouter: 'https://openrouter.ai/api/v1',
            xai: 'https://api.x.ai/v1',
        };

        this.baseURL = config.baseURL || defaultEndpoints[config.provider] || defaultEndpoints.openai;
        this.apiKey = config.apiKey;

        this.client = new OpenAI({
            apiKey: this.apiKey,
            baseURL: this.baseURL,
        });
    }

    async chat(messages: Message[], options?: ChatOptions): Promise<ChatResponse> {
        const response = await this.client.chat.completions.create({
            model: this.model,
            messages: messages.map((m) => this.toOpenAIMessage(m)),
            temperature: options?.temperature,
            max_tokens: options?.maxTokens,
            top_p: options?.topP,
            stop: options?.stop,
        });

        const choice = response.choices[0];
        return {
            id: response.id || this.generateId(),
            content: choice?.message?.content || '',
            finishReason: this.mapFinishReason(choice?.finish_reason),
            usage: response.usage
                ? {
                    promptTokens: response.usage.prompt_tokens,
                    completionTokens: response.usage.completion_tokens,
                    totalTokens: response.usage.total_tokens,
                }
                : undefined,
        };
    }

    async chatWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: ChatOptions
    ): Promise<ToolCallResponse> {
        const response = await this.client.chat.completions.create({
            model: this.model,
            messages: messages.map((m) => this.toOpenAIMessage(m)),
            tools: tools.map((t) => ({
                type: 'function' as const,
                function: t.function,
            })),
            tool_choice: 'auto',
            temperature: options?.temperature,
            max_tokens: options?.maxTokens,
        });

        const choice = response.choices[0];
        const message = choice?.message;

        return {
            id: response.id || this.generateId(),
            content: message?.content || '',
            finishReason: this.mapFinishReason(choice?.finish_reason),
            toolCalls: message?.tool_calls?.map((tc) => ({
                id: tc.id,
                type: 'function' as const,
                function: {
                    name: tc.function.name,
                    arguments: tc.function.arguments,
                },
            })),
            usage: response.usage
                ? {
                    promptTokens: response.usage.prompt_tokens,
                    completionTokens: response.usage.completion_tokens,
                    totalTokens: response.usage.total_tokens,
                }
                : undefined,
        };
    }

    /**
     * 流式聊天
     */
    async *chatStream(
        messages: Message[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown> {
        const stream = await this.client.chat.completions.create({
            model: this.model,
            messages: messages.map((m) => this.toOpenAIMessage(m)),
            temperature: options?.temperature,
            max_tokens: options?.maxTokens,
            top_p: options?.topP,
            stop: options?.stop,
            stream: true,
            stream_options: options?.includeUsage ? { include_usage: true } : undefined,
        });

        for await (const chunk of stream) {
            // 检查中止信号
            if (options?.signal?.aborted) {
                break;
            }

            const choice = chunk.choices[0];
            const delta = choice?.delta as {
                content?: string | null;
                reasoning_content?: string;
            } | undefined;

            const streamChunk: StreamChunk = {};

            // 处理文本内容
            if (delta?.content) {
                streamChunk.content = delta.content;
            }

            // 处理推理内容 (DeepSeek 等模型)
            if (delta?.reasoning_content) {
                streamChunk.reasoningContent = delta.reasoning_content;
            }

            // 处理完成原因
            if (choice?.finish_reason) {
                streamChunk.finishReason = this.mapFinishReason(choice.finish_reason);
            }

            // 处理 usage (通常在最后一个 chunk)
            if (chunk.usage) {
                streamChunk.usage = {
                    promptTokens: chunk.usage.prompt_tokens,
                    completionTokens: chunk.usage.completion_tokens,
                    totalTokens: chunk.usage.total_tokens,
                };
            }

            // 只有有内容时才 yield
            if (streamChunk.content || streamChunk.reasoningContent ||
                streamChunk.finishReason || streamChunk.usage) {
                yield streamChunk;
            }
        }
    }

    /**
     * 流式带工具调用的聊天
     */
    async *chatStreamWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown> {
        const stream = await this.client.chat.completions.create({
            model: this.model,
            messages: messages.map((m) => this.toOpenAIMessage(m)),
            tools: tools.map((t) => ({
                type: 'function' as const,
                function: t.function,
            })),
            tool_choice: 'auto',
            temperature: options?.temperature,
            max_tokens: options?.maxTokens,
            stream: true,
            stream_options: options?.includeUsage ? { include_usage: true } : undefined,
        });

        for await (const chunk of stream) {
            // 检查中止信号
            if (options?.signal?.aborted) {
                break;
            }

            const choice = chunk.choices[0];
            const delta = choice?.delta as {
                content?: string | null;
                reasoning_content?: string;
                tool_calls?: Array<{
                    index: number;
                    id?: string;
                    type?: 'function';
                    function?: {
                        name?: string;
                        arguments?: string;
                    };
                }>;
            } | undefined;

            const streamChunk: StreamChunk = {};

            // 处理文本内容
            if (delta?.content) {
                streamChunk.content = delta.content;
            }

            // 处理推理内容
            if (delta?.reasoning_content) {
                streamChunk.reasoningContent = delta.reasoning_content;
            }

            // 处理工具调用增量
            if (delta?.tool_calls && delta.tool_calls.length > 0) {
                streamChunk.toolCalls = delta.tool_calls.map((tc): ToolCallDelta => ({
                    index: tc.index,
                    id: tc.id,
                    type: tc.type,
                    function: tc.function ? {
                        name: tc.function.name,
                        arguments: tc.function.arguments,
                    } : undefined,
                }));
            }

            // 处理完成原因
            if (choice?.finish_reason) {
                streamChunk.finishReason = this.mapFinishReason(choice.finish_reason);
            }

            // 处理 usage
            if (chunk.usage) {
                streamChunk.usage = {
                    promptTokens: chunk.usage.prompt_tokens,
                    completionTokens: chunk.usage.completion_tokens,
                    totalTokens: chunk.usage.total_tokens,
                };
            }

            // 只有有内容时才 yield
            if (streamChunk.content || streamChunk.reasoningContent ||
                streamChunk.toolCalls || streamChunk.finishReason || streamChunk.usage) {
                yield streamChunk;
            }
        }
    }

    supportsVision(): boolean {
        // 视觉模型通常在名称中包含 vision 或 4o
        const visionModels = ['gpt-4o', 'gpt-4-vision', 'gpt-4-turbo'];
        return visionModels.some((v) => this.model.includes(v));
    }

    supportsStreaming(): boolean {
        return true; // OpenAI 兼容引擎都支持流式
    }

    getMaxTokens(): number {
        if (this.model.includes('gpt-4')) return 128000;
        if (this.model.includes('gpt-3.5')) return 16384;
        if (this.model.includes('deepseek')) return 64000;
        return 4096;
    }

    getConfigInfo(): { model: string; apiUrl: string; isConfigured: boolean } {
        return {
            model: this.model,
            apiUrl: this.baseURL,
            isConfigured: !!this.apiKey,
        };
    }

    private mapFinishReason(
        reason?: string | null
    ): 'stop' | 'length' | 'tool_calls' | 'content_filter' | null {
        if (!reason) return null;
        if (reason === 'stop') return 'stop';
        if (reason === 'length') return 'length';
        if (reason === 'tool_calls') return 'tool_calls';
        if (reason === 'content_filter') return 'content_filter';
        return null;
    }

    private toOpenAIMessage(message: Message): any {
        // Multi-modal content is only supported by some OpenAI-compatible providers/models.
        // When images are present, prefer structured content parts.
        if (message.role === 'user' && message.images && message.images.length > 0) {
            const parts: any[] = [];
            if (message.content) {
                parts.push({ type: 'text', text: message.content });
            }

            for (const image of message.images) {
                const normalized = normalizeBase64Image(image);
                parts.push({
                    type: 'image_url',
                    image_url: { url: toDataUrl(normalized) },
                });
            }

            return {
                role: 'user',
                content: parts,
            };
        }

        const payload: Record<string, unknown> = {
            role: message.role as 'system' | 'user' | 'assistant' | 'tool',
            content: message.content,
        };
        if (message.name) {
            payload.name = message.name;
        }
        if (message.toolCallId) {
            payload.tool_call_id = message.toolCallId;
        }
        return payload;
    }
}
