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

// ============ 流式响应类型定义 ============

/** 工具调用增量 (流式) */
export interface ToolCallDelta {
    index: number;
    id?: string;
    type?: 'function';
    function?: {
        name?: string;
        arguments?: string;
    };
}

/** 流式响应块 */
export interface StreamChunk {
    /** 文本内容增量 */
    content?: string;
    /** 推理内容增量 (DeepSeek 等模型) */
    reasoningContent?: string;
    /** 工具调用增量 */
    toolCalls?: ToolCallDelta[];
    /** 完成原因 */
    finishReason?: 'stop' | 'tool_calls' | 'length' | 'content_filter' | null;
    /** Token 使用情况 (通常在最后一个 chunk) */
    usage?: {
        promptTokens: number;
        completionTokens: number;
        totalTokens: number;
    };
}

/** 流式选项 */
export interface StreamOptions extends ChatOptions {
    /** 是否包含 usage 信息 (需要模型支持) */
    includeUsage?: boolean;
    /** 中止信号 */
    signal?: AbortSignal;
}

/** 流式处理状态 */
export interface StreamProcessingState {
    /** 内容缓冲区 */
    contentBuffer: string;
    /** 推理内容缓冲区 */
    reasoningBuffer: string;
    /** 工具调用累积 */
    toolCalls: Map<number, ToolCall>;
    /** 是否已完成 */
    finished: boolean;
    /** 完成原因 */
    finishReason?: StreamChunk['finishReason'];
}

/** 创建初始流式处理状态 */
export function createStreamProcessingState(): StreamProcessingState {
    return {
        contentBuffer: '',
        reasoningBuffer: '',
        toolCalls: new Map(),
        finished: false,
    };
}

/** 合并工具调用增量到状态 */
export function mergeToolCallDelta(
    state: StreamProcessingState,
    delta: ToolCallDelta
): void {
    const existing = state.toolCalls.get(delta.index);
    if (existing) {
        // 累积 arguments
        if (delta.function?.arguments) {
            existing.function.arguments += delta.function.arguments;
        }
    } else if (delta.id && delta.function?.name) {
        // 新工具调用
        state.toolCalls.set(delta.index, {
            id: delta.id,
            type: 'function',
            function: {
                name: delta.function.name,
                arguments: delta.function.arguments || '',
            },
        });
    }
}

// ============ AI 引擎接口 ============

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

    /** 流式聊天 */
    chatStream(
        messages: Message[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown>;

    /** 流式带工具调用的聊天 */
    chatStreamWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: StreamOptions
    ): AsyncGenerator<StreamChunk, void, unknown>;

    /** 检测能力 */
    supportsVision(): boolean;
    supportsToolCalling(): boolean;
    supportsStreaming(): boolean;
    getMaxTokens(): number;
}
