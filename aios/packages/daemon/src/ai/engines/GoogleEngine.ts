/**
 * Google Gemini 引擎
 */

import { GoogleGenerativeAI, SchemaType, type Content } from '@google/generative-ai';
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
} from '@aios/shared';
import { normalizeBase64Image } from '../utils/images.js';

export interface GoogleConfig {
    model: string;
    apiKey: string;
}

export class GoogleEngine extends BaseAIEngine {
    readonly id: string;
    readonly name: string;
    readonly provider: AIProvider = AIProvider.GOOGLE;
    readonly model: string;

    private genAI: GoogleGenerativeAI;
    private apiKey: string;

    constructor(config: GoogleConfig) {
        super();
        this.model = config.model;
        this.id = `google/${config.model}`;
        this.name = `Google - ${config.model}`;
        this.apiKey = config.apiKey;

        this.genAI = new GoogleGenerativeAI(this.apiKey);
    }

    async chat(messages: Message[], options?: ChatOptions): Promise<ChatResponse> {
        const model = this.genAI.getGenerativeModel({
            model: this.model,
            generationConfig: {
                temperature: options?.temperature,
                maxOutputTokens: options?.maxTokens,
                topP: options?.topP,
                stopSequences: options?.stop,
            },
        });

        // 转换消息格式
        const systemInstruction = messages.find((m) => m.role === 'system')?.content;
        const history = this.convertToGeminiHistory(messages.filter((m) => m.role !== 'system'));

        const chat = model.startChat({
            history: history.slice(0, -1),
            systemInstruction,
        });

        const lastMessage = history[history.length - 1];
        const result = await chat.sendMessage(lastMessage?.parts || '');

        const response = result.response;
        return {
            id: this.generateId(),
            content: response.text(),
            finishReason: this.mapFinishReason(response.candidates?.[0]?.finishReason),
            usage: response.usageMetadata
                ? {
                    promptTokens: response.usageMetadata.promptTokenCount || 0,
                    completionTokens: response.usageMetadata.candidatesTokenCount || 0,
                    totalTokens: response.usageMetadata.totalTokenCount || 0,
                }
                : undefined,
        };
    }

    async chatWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: ChatOptions
    ): Promise<ToolCallResponse> {
        const model = this.genAI.getGenerativeModel({
            model: this.model,
            tools: [
                {
                    functionDeclarations: tools.map((t) => ({
                        name: t.function.name,
                        description: t.function.description,
                        parameters: {
                            type: SchemaType.OBJECT,
                            properties: Object.fromEntries(
                                Object.entries(t.function.parameters.properties).map(([key, value]) => [
                                    key,
                                    {
                                        type: this.mapType(value.type),
                                        description: value.description,
                                    },
                                ])
                            ),
                            required: t.function.parameters.required || [],
                        },
                    })),
                },
            ],
            generationConfig: {
                temperature: options?.temperature,
                maxOutputTokens: options?.maxTokens,
            },
        });

        const systemInstruction = messages.find((m) => m.role === 'system')?.content;
        const history = this.convertToGeminiHistory(messages.filter((m) => m.role !== 'system'));

        const chat = model.startChat({
            history: history.slice(0, -1),
            systemInstruction,
        });

        const lastMessage = history[history.length - 1];
        const result = await chat.sendMessage(lastMessage?.parts || '');
        const response = result.response;

        const functionCalls = response.functionCalls();

        return {
            id: this.generateId(),
            content: response.text(),
            finishReason: this.mapFinishReason(response.candidates?.[0]?.finishReason),
            toolCalls: functionCalls?.map((fc, index) => ({
                id: `call_${index}`,
                type: 'function' as const,
                function: {
                    name: fc.name,
                    arguments: JSON.stringify(fc.args),
                },
            })),
            usage: response.usageMetadata
                ? {
                    promptTokens: response.usageMetadata.promptTokenCount || 0,
                    completionTokens: response.usageMetadata.candidatesTokenCount || 0,
                    totalTokens: response.usageMetadata.totalTokenCount || 0,
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
        const model = this.genAI.getGenerativeModel({
            model: this.model,
            generationConfig: {
                temperature: options?.temperature,
                maxOutputTokens: options?.maxTokens,
                topP: options?.topP,
                stopSequences: options?.stop,
            },
        });

        const systemInstruction = messages.find((m) => m.role === 'system')?.content;
        const history = this.convertToGeminiHistory(messages.filter((m) => m.role !== 'system'));

        const chat = model.startChat({
            history: history.slice(0, -1),
            systemInstruction,
        });

        const lastMessage = history[history.length - 1];
        const result = await chat.sendMessageStream(lastMessage?.parts || '');

        for await (const chunk of result.stream) {
            // 检查中止信号
            if (options?.signal?.aborted) {
                break;
            }

            const text = chunk.text();
            const candidate = chunk.candidates?.[0];

            const streamChunk: StreamChunk = {};

            if (text) {
                streamChunk.content = text;
            }

            if (candidate?.finishReason) {
                streamChunk.finishReason = this.mapFinishReason(candidate.finishReason);
            }

            // 只有有内容时才 yield
            if (streamChunk.content || streamChunk.finishReason) {
                yield streamChunk;
            }
        }

        // 获取最终的 usage 信息
        const finalResponse = await result.response;
        if (finalResponse.usageMetadata) {
            yield {
                usage: {
                    promptTokens: finalResponse.usageMetadata.promptTokenCount || 0,
                    completionTokens: finalResponse.usageMetadata.candidatesTokenCount || 0,
                    totalTokens: finalResponse.usageMetadata.totalTokenCount || 0,
                },
            };
        }
    }

    /**
     * 流式带工具调用的聊天
     * 注意：Gemini 的流式模式对工具调用支持有限，这里使用非流式模拟
     */
    async *chatStreamWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown> {
        // Gemini 的流式工具调用支持有限，使用父类默认实现（非流式模拟）
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
            usage: response.usage,
        };
    }

    supportsVision(): boolean {
        // Gemini Pro Vision 和 2.5 Flash 支持视觉
        return this.model.includes('vision') || this.model.includes('flash') || this.model.includes('pro');
    }

    supportsStreaming(): boolean {
        return true; // Gemini 支持流式
    }

    getMaxTokens(): number {
        if (this.model.includes('2.5')) return 1000000;
        if (this.model.includes('1.5-pro')) return 2000000;
        return 32000;
    }

    getConfigInfo(): { model: string; apiUrl: string; isConfigured: boolean } {
        return {
            model: this.model,
            apiUrl: 'https://generativelanguage.googleapis.com/v1beta',
            isConfigured: !!this.apiKey,
        };
    }

    private convertToGeminiHistory(messages: Message[]): Content[] {
        return messages.map((m) => {
            const parts: Content['parts'] = [];

            if (m.content) {
                parts.push({ text: m.content });
            }

            for (const image of m.images ?? []) {
                const normalized = normalizeBase64Image(image);
                parts.push({ inlineData: { mimeType: normalized.mimeType, data: normalized.data } });
            }

            return {
                role: m.role === 'assistant' ? 'model' : 'user',
                parts,
            };
        });
    }

    private mapType(type: string): SchemaType {
        switch (type) {
            case 'string':
                return SchemaType.STRING;
            case 'number':
                return SchemaType.NUMBER;
            case 'boolean':
                return SchemaType.BOOLEAN;
            case 'array':
                return SchemaType.ARRAY;
            case 'object':
                return SchemaType.OBJECT;
            default:
                return SchemaType.STRING;
        }
    }

    private mapFinishReason(
        reason?: string
    ): 'stop' | 'length' | 'tool_calls' | 'content_filter' | null {
        if (!reason) return null;
        if (reason === 'STOP') return 'stop';
        if (reason === 'MAX_TOKENS') return 'length';
        if (reason === 'SAFETY') return 'content_filter';
        return null;
    }
}
