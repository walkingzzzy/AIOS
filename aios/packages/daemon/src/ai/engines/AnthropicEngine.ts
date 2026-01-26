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
    type StreamChunk,
    type StreamOptions,
    type ToolCallDelta,
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

    /**
     * 流式聊天
     */
    async *chatStream(
        messages: Message[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown> {
        const systemMessage = messages.find((m) => m.role === 'system');
        const chatMessages = messages.filter((m) => m.role !== 'system');

        const stream = this.client.messages.stream({
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

        for await (const event of stream) {
            // 检查中止信号
            if (options?.signal?.aborted) {
                stream.controller.abort();
                break;
            }

            if (event.type === 'content_block_delta') {
                const delta = event.delta;
                if (delta.type === 'text_delta') {
                    yield { content: delta.text };
                }
            } else if (event.type === 'message_stop') {
                // 流结束
            } else if (event.type === 'message_delta') {
                if (event.delta.stop_reason) {
                    yield { finishReason: this.mapStopReason(event.delta.stop_reason) };
                }
            }
        }

        // 获取最终消息以获取 usage
        const finalMessage = await stream.finalMessage();
        if (finalMessage.usage) {
            yield {
                usage: {
                    promptTokens: finalMessage.usage.input_tokens,
                    completionTokens: finalMessage.usage.output_tokens,
                    totalTokens: finalMessage.usage.input_tokens + finalMessage.usage.output_tokens,
                },
            };
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
        const systemMessage = messages.find((m) => m.role === 'system');
        const chatMessages = messages.filter((m) => m.role !== 'system');

        const stream = this.client.messages.stream({
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

        // 用于累积工具调用
        const toolCallState = new Map<number, { id: string; name: string; arguments: string }>();
        let currentToolIndex = -1;

        for await (const event of stream) {
            if (options?.signal?.aborted) {
                stream.controller.abort();
                break;
            }

            if (event.type === 'content_block_start') {
                const block = event.content_block;
                if (block.type === 'tool_use') {
                    currentToolIndex = event.index;
                    toolCallState.set(currentToolIndex, {
                        id: block.id,
                        name: block.name,
                        arguments: '',
                    });
                    yield {
                        toolCalls: [{
                            index: currentToolIndex,
                            id: block.id,
                            type: 'function',
                            function: { name: block.name },
                        }],
                    };
                }
            } else if (event.type === 'content_block_delta') {
                const delta = event.delta;
                if (delta.type === 'text_delta') {
                    yield { content: delta.text };
                } else if (delta.type === 'input_json_delta') {
                    const toolCall = toolCallState.get(event.index);
                    if (toolCall) {
                        toolCall.arguments += delta.partial_json;
                        yield {
                            toolCalls: [{
                                index: event.index,
                                function: { arguments: delta.partial_json },
                            }],
                        };
                    }
                }
            } else if (event.type === 'message_delta') {
                if (event.delta.stop_reason) {
                    yield { finishReason: this.mapStopReason(event.delta.stop_reason) };
                }
            }
        }

        // 获取 usage
        const finalMessage = await stream.finalMessage();
        if (finalMessage.usage) {
            yield {
                usage: {
                    promptTokens: finalMessage.usage.input_tokens,
                    completionTokens: finalMessage.usage.output_tokens,
                    totalTokens: finalMessage.usage.input_tokens + finalMessage.usage.output_tokens,
                },
            };
        }
    }

    supportsVision(): boolean {
        // Claude 3 系列支持视觉
        return this.model.includes('claude-3');
    }

    supportsStreaming(): boolean {
        return true; // Claude 支持流式
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

