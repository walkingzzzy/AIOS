/**
 * Anthropic Claude 引擎
 */

import Anthropic from '@anthropic-ai/sdk';
import { BaseAIEngine } from '../AIEngine.js';
import {
    AIProvider,
    type Message,
    type ChatOptions,
    type ChatResponse,
    type ToolDefinition,
    type ToolCallResponse,
} from '@aios/shared';
import { normalizeBase64Image } from '../utils/images.js';

export interface AnthropicConfig {
    model: string;
    apiKey: string;
}

export class AnthropicEngine extends BaseAIEngine {
    readonly id: string;
    readonly name: string;
    readonly provider: AIProvider = AIProvider.ANTHROPIC;
    readonly model: string;

    private client: Anthropic;
    private apiKey: string;

    constructor(config: AnthropicConfig) {
        super();
        this.model = config.model;
        this.id = `anthropic/${config.model}`;
        this.name = `Anthropic - ${config.model}`;
        this.apiKey = config.apiKey;

        this.client = new Anthropic({
            apiKey: this.apiKey,
        });
    }

    async chat(messages: Message[], options?: ChatOptions): Promise<ChatResponse> {
        // 提取系统消息
        const systemMessage = messages.find((m) => m.role === 'system');
        const chatMessages = messages.filter((m) => m.role !== 'system');

        const response = await this.client.messages.create({
            model: this.model,
            max_tokens: options?.maxTokens || 4096,
            system: systemMessage?.content,
            messages: chatMessages.map((m) => ({
                role: m.role as 'user' | 'assistant',
                content: this.toAnthropicContent(m),
            })),
            temperature: options?.temperature,
            top_p: options?.topP,
            stop_sequences: options?.stop,
        });

        const textBlock = response.content.find((c) => c.type === 'text');
        return {
            id: response.id,
            content: textBlock?.type === 'text' ? textBlock.text : '',
            finishReason: this.mapStopReason(response.stop_reason),
            usage: {
                promptTokens: response.usage.input_tokens,
                completionTokens: response.usage.output_tokens,
                totalTokens: response.usage.input_tokens + response.usage.output_tokens,
            },
        };
    }

    async chatWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: ChatOptions
    ): Promise<ToolCallResponse> {
        const systemMessage = messages.find((m) => m.role === 'system');
        const chatMessages = messages.filter((m) => m.role !== 'system');

        const response = await this.client.messages.create({
            model: this.model,
            max_tokens: options?.maxTokens || 4096,
            system: systemMessage?.content,
            messages: chatMessages.map((m) => ({
                role: m.role as 'user' | 'assistant',
                content: this.toAnthropicContent(m),
            })),
            tools: tools.map((t) => ({
                name: t.function.name,
                description: t.function.description,
                input_schema: t.function.parameters as Anthropic.Tool.InputSchema,
            })),
            temperature: options?.temperature,
        });

        const textBlock = response.content.find((c) => c.type === 'text');
        const toolUseBlocks = response.content.filter((c) => c.type === 'tool_use');

        return {
            id: response.id,
            content: textBlock?.type === 'text' ? textBlock.text : '',
            finishReason: this.mapStopReason(response.stop_reason),
            toolCalls: toolUseBlocks.map((block) => {
                if (block.type !== 'tool_use') throw new Error('Unexpected block type');
                return {
                    id: block.id,
                    type: 'function' as const,
                    function: {
                        name: block.name,
                        arguments: JSON.stringify(block.input),
                    },
                };
            }),
            usage: {
                promptTokens: response.usage.input_tokens,
                completionTokens: response.usage.output_tokens,
                totalTokens: response.usage.input_tokens + response.usage.output_tokens,
            },
        };
    }

    supportsVision(): boolean {
        // Claude 3 系列支持视觉
        return this.model.includes('claude-3');
    }

    getMaxTokens(): number {
        if (this.model.includes('opus')) return 200000;
        if (this.model.includes('sonnet')) return 200000;
        if (this.model.includes('haiku')) return 200000;
        return 100000;
    }

    getConfigInfo(): { model: string; apiUrl: string; isConfigured: boolean } {
        return {
            model: this.model,
            apiUrl: 'https://api.anthropic.com/v1',
            isConfigured: !!this.apiKey,
        };
    }

    private mapStopReason(
        reason?: string | null
    ): 'stop' | 'length' | 'tool_calls' | 'content_filter' | null {
        if (!reason) return null;
        if (reason === 'end_turn') return 'stop';
        if (reason === 'max_tokens') return 'length';
        if (reason === 'tool_use') return 'tool_calls';
        return null;
    }

    private toAnthropicContent(message: Message): any {
        if (!message.images || message.images.length === 0) {
            return message.content;
        }

        const blocks: any[] = [];
        if (message.content) {
            blocks.push({ type: 'text', text: message.content });
        }

        for (const image of message.images) {
            const normalized = normalizeBase64Image(image);
            blocks.push({
                type: 'image',
                source: {
                    type: 'base64',
                    media_type: normalized.mimeType,
                    data: normalized.data,
                },
            });
        }

        return blocks;
    }
}
