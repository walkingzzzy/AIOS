/**
 * AI 引擎相关类型定义
 */

/** AI 提供商枚举 */
export enum AIProvider {
    OPENAI = 'openai',
    ANTHROPIC = 'anthropic',
    GOOGLE = 'google',
    MISTRAL = 'mistral',
    DEEPSEEK = 'deepseek',
    QWEN = 'qwen',
    META = 'meta',
    XAI = 'xai',
    COHERE = 'cohere',
    OPENROUTER = 'openrouter',
    TOGETHER = 'together',
    GROQ = 'groq',
    CUSTOM = 'custom',
}

/** OpenAI 兼容的提供商端点 */
export const OPENAI_COMPATIBLE_ENDPOINTS: Record<string, string> = {
    openai: 'https://api.openai.com/v1',
    deepseek: 'https://api.deepseek.com/v1',
    qwen: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    mistral: 'https://api.mistral.ai/v1',
    groq: 'https://api.groq.com/openai/v1',
    together: 'https://api.together.xyz/v1',
    openrouter: 'https://openrouter.ai/api/v1',
    xai: 'https://api.x.ai/v1',
};

/** 消息角色 */
export type MessageRole = 'system' | 'user' | 'assistant' | 'tool';

/** 聊天消息 */
export interface Message {
    role: MessageRole;
    content: string;
    name?: string;
    toolCallId?: string;
    images?: string[];  // base64 编码的图像
}

/** 工具定义 (OpenAI 格式) */
export interface ToolDefinition {
    type: 'function';
    function: {
        name: string;
        description: string;
        parameters: {
            type: 'object';
            properties: Record<string, {
                type: string;
                description: string;
                enum?: string[];
            }>;
            required?: string[];
        };
    };
}

/** 内部工具定义 (简化格式) */
export interface InternalToolDefinition {
    name: string;
    description: string;
    parameters?: Record<string, unknown>;
}

/** 将内部工具定义转换为 OpenAI 格式 */
export function toOpenAIToolDefinition(tool: InternalToolDefinition): ToolDefinition {
    const params = tool.parameters as {
        type?: string;
        properties?: Record<string, unknown>;
        required?: string[];
    } | undefined;
    
    return {
        type: 'function',
        function: {
            name: tool.name,
            description: tool.description,
            parameters: {
                type: 'object',
                properties: (params?.properties || {}) as Record<string, { type: string; description: string; enum?: string[] }>,
                required: params?.required || [],
            },
        },
    };
}

/** 工具调用 */
export interface ToolCall {
    id: string;
    type: 'function';
    function: {
        name: string;
        arguments: string;
    };
}

/** 聊天选项 */
export interface ChatOptions {
    temperature?: number;
    maxTokens?: number;
    topP?: number;
    stop?: string[];
    stream?: boolean;
}

/** 聊天响应 */
export interface ChatResponse {
    id: string;
    content: string;
    finishReason: 'stop' | 'length' | 'tool_calls' | 'content_filter' | null;
    usage?: {
        promptTokens: number;
        completionTokens: number;
        totalTokens: number;
    };
}

/** 工具调用响应 */
export interface ToolCallResponse extends ChatResponse {
    toolCalls?: ToolCall[];
}

/** AI 引擎配置 */
export interface AIEngineConfig {
    provider: AIProvider;
    model: string;
    apiKey: string;
    baseURL?: string;
    defaultOptions?: ChatOptions;
}

/** 三层路由配置 */
export interface AIRouterConfig {
    fast: AIEngineConfig;
    vision: AIEngineConfig;
    smart: AIEngineConfig;
}

/** AI 引擎接口 */
export interface IAIEngine {
    readonly id: string;
    readonly name: string;
    readonly provider: AIProvider;
    readonly model: string;

    /** 基础聊天 */
    chat(messages: Message[], options?: ChatOptions): Promise<ChatResponse>;

    /** 带工具调用的聊天 */
    chatWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: ChatOptions
    ): Promise<ToolCallResponse>;

    /** 检测能力 */
    supportsVision(): boolean;
    supportsToolCalling(): boolean;
    getMaxTokens(): number;
}
