/**
 * AI 引擎注册表
 * 管理所有已注册的 AI 引擎实例
 */

import type { IAIEngine, AIEngineConfig } from '@aios/shared';
import { AIProvider } from '@aios/shared';
import { OpenAICompatibleEngine, AnthropicEngine, GoogleEngine } from './engines/index.js';

export class EngineRegistry {
    private engines: Map<string, IAIEngine> = new Map();

    /** 注册引擎 */
    register(engine: IAIEngine): void {
        this.engines.set(engine.id, engine);
    }

    /** 获取引擎 */
    get(id: string): IAIEngine | undefined {
        return this.engines.get(id);
    }

    /** 获取所有引擎 */
    getAll(): IAIEngine[] {
        return Array.from(this.engines.values());
    }

    /** 按提供商获取引擎 */
    getByProvider(provider: AIProvider): IAIEngine[] {
        return this.getAll().filter((e) => e.provider === provider);
    }

    /** 根据配置创建并注册引擎 */
    createFromConfig(config: AIEngineConfig): IAIEngine {
        let engine: IAIEngine;

        switch (config.provider) {
            case AIProvider.ANTHROPIC:
                engine = new AnthropicEngine({
                    model: config.model,
                    apiKey: config.apiKey,
                });
                break;

            case AIProvider.GOOGLE:
                engine = new GoogleEngine({
                    model: config.model,
                    apiKey: config.apiKey,
                });
                break;

            // OpenAI 兼容的提供商
            case AIProvider.OPENAI:
            case AIProvider.DEEPSEEK:
            case AIProvider.QWEN:
            case AIProvider.MISTRAL:
            case AIProvider.GROQ:
            case AIProvider.TOGETHER:
            case AIProvider.OPENROUTER:
            case AIProvider.XAI:
            case AIProvider.CUSTOM:
            default:
                engine = new OpenAICompatibleEngine({
                    provider: config.provider,
                    model: config.model,
                    apiKey: config.apiKey,
                    baseURL: config.baseURL,
                });
                break;
        }

        this.register(engine);
        return engine;
    }

    /** 清空所有引擎 */
    clear(): void {
        this.engines.clear();
    }
}

/** 全局引擎注册表实例 */
export const engineRegistry = new EngineRegistry();
