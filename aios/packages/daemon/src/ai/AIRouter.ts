/**
 * AI 路由器
 * 根据意图分类将请求路由到合适的 AI 层
 */

import type {
    IAIEngine,
    AIRouterConfig,
    Message,
    ChatOptions,
    ChatResponse,
    ToolDefinition,
    ToolCallResponse,
} from '@aios/shared';
import { EngineRegistry } from './EngineRegistry.js';
import { IntentClassifier, type IntentType } from './IntentClassifier.js';

export interface AIRouterOptions {
    config: AIRouterConfig;
    registry?: EngineRegistry;
    classifier?: IntentClassifier;
}

export class AIRouter {
    private registry: EngineRegistry;
    private classifier: IntentClassifier;
    private engines: {
        fast: IAIEngine;
        vision: IAIEngine;
        smart: IAIEngine;
    };

    constructor(options: AIRouterOptions) {
        this.registry = options.registry || new EngineRegistry();
        this.classifier = options.classifier || new IntentClassifier();

        // 创建三层引擎
        this.engines = {
            fast: this.registry.createFromConfig(options.config.fast),
            vision: this.registry.createFromConfig(options.config.vision),
            smart: this.registry.createFromConfig(options.config.smart),
        };
    }

    /** 根据意图选择引擎 */
    private selectEngine(intentType: IntentType): IAIEngine {
        switch (intentType) {
            case 'simple':
                return this.engines.fast;
            case 'visual':
                return this.engines.vision;
            case 'complex':
                return this.engines.smart;
            default:
                return this.engines.fast;
        }
    }

    /** 智能聊天 - 自动路由到合适的层 */
    async chat(messages: Message[], options?: ChatOptions): Promise<ChatResponse & { layer: IntentType }> {
        const userMessage = messages.filter((m) => m.role === 'user').pop();
        const classification = this.classifier.classify(userMessage?.content || '');

        const engine = this.selectEngine(classification.type);
        const response = await engine.chat(messages, options);

        return {
            ...response,
            layer: classification.type,
        };
    }

    /** 带工具调用的智能聊天 */
    async chatWithTools(
        messages: Message[],
        tools: ToolDefinition[],
        options?: ChatOptions
    ): Promise<ToolCallResponse & { layer: IntentType }> {
        const userMessage = messages.filter((m) => m.role === 'user').pop();
        const classification = this.classifier.classify(userMessage?.content || '');

        const engine = this.selectEngine(classification.type);
        const response = await engine.chatWithTools(messages, tools, options);

        return {
            ...response,
            layer: classification.type,
        };
    }

    /** 强制使用指定层 */
    async chatWithLayer(
        layer: IntentType,
        messages: Message[],
        options?: ChatOptions
    ): Promise<ChatResponse> {
        const engine = this.selectEngine(layer);
        return engine.chat(messages, options);
    }

    /** 获取引擎信息 */
    getEngineInfo() {
        return {
            fast: {
                id: this.engines.fast.id,
                name: this.engines.fast.name,
                provider: this.engines.fast.provider,
            },
            vision: {
                id: this.engines.vision.id,
                name: this.engines.vision.name,
                provider: this.engines.vision.provider,
            },
            smart: {
                id: this.engines.smart.id,
                name: this.engines.smart.name,
                provider: this.engines.smart.provider,
            },
        };
    }
}
