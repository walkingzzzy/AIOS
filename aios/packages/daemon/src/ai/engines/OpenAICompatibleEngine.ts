/**
 * OpenAI 兼容引擎
 * 支持: OpenAI, DeepSeek, Qwen, Mistral, Groq, Together, OpenRouter, xAI
 */

import OpenAI from 'openai';
import { BaseAIEngine } from '../AIEngine.js';
import type {
    AIProvider,
    Message,
    ChatOptions,
    ChatResponse,
    ToolDefinition,
    ToolCallResponse,
    OPENAI_COMPATIBLE_ENDPOINTS,
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

        const baseURL = config.baseURL || defaultEndpoints[config.provider] || defaultEndpoints.openai;

        this.client = new OpenAI({
            apiKey: config.apiKey,
            baseURL,
        });
    }

    async chat(messages: Message[], options?: ChatOptions): Promise<ChatResponse> {
        const response = await this.client.chat.completions.create({
            model: this.model,
            messages: messages.map((m) => ({
                role: m.role as 'system' | 'user' | 'assistant',
                content: m.content,
            })),
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
            messages: messages.map((m) => ({
                role: m.role as 'system' | 'user' | 'assistant',
                content: m.content,
            })),
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

    supportsVision(): boolean {
        // 视觉模型通常在名称中包含 vision 或 4o
        const visionModels = ['gpt-4o', 'gpt-4-vision', 'gpt-4-turbo'];
        return visionModels.some((v) => this.model.includes(v));
    }

    getMaxTokens(): number {
        if (this.model.includes('gpt-4')) return 128000;
        if (this.model.includes('gpt-3.5')) return 16384;
        if (this.model.includes('deepseek')) return 64000;
        return 4096;
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
}
