/**
 * Google Gemini 引擎
 */

import { GoogleGenerativeAI, SchemaType } from '@google/generative-ai';
import { BaseAIEngine } from '../AIEngine.js';
import type {
    AIProvider,
    Message,
    ChatOptions,
    ChatResponse,
    ToolDefinition,
    ToolCallResponse,
} from '@aios/shared';

export interface GoogleConfig {
    model: string;
    apiKey: string;
}

export class GoogleEngine extends BaseAIEngine {
    readonly id: string;
    readonly name: string;
    readonly provider: AIProvider = 'google';
    readonly model: string;

    private genAI: GoogleGenerativeAI;

    constructor(config: GoogleConfig) {
        super();
        this.model = config.model;
        this.id = `google/${config.model}`;
        this.name = `Google - ${config.model}`;

        this.genAI = new GoogleGenerativeAI(config.apiKey);
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

    supportsVision(): boolean {
        // Gemini Pro Vision 和 2.5 Flash 支持视觉
        return this.model.includes('vision') || this.model.includes('flash') || this.model.includes('pro');
    }

    getMaxTokens(): number {
        if (this.model.includes('2.5')) return 1000000;
        if (this.model.includes('1.5-pro')) return 2000000;
        return 32000;
    }

    private convertToGeminiHistory(messages: Message[]) {
        return messages.map((m) => ({
            role: m.role === 'assistant' ? 'model' : 'user',
            parts: m.content,
        }));
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
