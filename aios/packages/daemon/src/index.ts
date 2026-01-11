/**
 * AIOS Daemon 主入口
 */

import type { AIRouterConfig } from '@aios/shared';
import { AIProvider } from '@aios/shared';
import { AIRouter } from './ai/index.js';
import { adapterRegistry, JSONRPCHandler, StdioTransport, WebSocketTransport, TaskOrchestrator } from './core/index.js';
import {
    audioAdapter,
    displayAdapter,
    desktopAdapter,
    powerAdapter,
    appsAdapter,
    systemInfoAdapter,
    fileAdapter,
    windowAdapter,
    browserAdapter,
    speechAdapter,
    notificationAdapter,
    timerAdapter,
    calculatorAdapter,
    calendarAdapter,
    weatherAdapter,
    translateAdapter,
} from './adapters/index.js';

// 默认 API URLs
const DEFAULT_URLS: Record<string, string> = {
    openai: 'https://api.openai.com/v1',
    anthropic: 'https://api.anthropic.com/v1',
    google: 'https://generativelanguage.googleapis.com/v1beta',
    deepseek: 'https://api.deepseek.com/v1',
    groq: 'https://api.groq.com/openai/v1',
};

// 默认 AI 配置 (可通过环境变量覆盖)
function getDefaultAIConfig(): AIRouterConfig {
    const parseProvider = (envValue: string | undefined, defaultValue: AIProvider): AIProvider => {
        if (!envValue) return defaultValue;
        const providerMap: Record<string, AIProvider> = {
            openai: AIProvider.OPENAI,
            anthropic: AIProvider.ANTHROPIC,
            google: AIProvider.GOOGLE,
            deepseek: AIProvider.DEEPSEEK,
            groq: AIProvider.GROQ,
            qwen: AIProvider.QWEN,
            mistral: AIProvider.MISTRAL,
            together: AIProvider.TOGETHER,
            openrouter: AIProvider.OPENROUTER,
            xai: AIProvider.XAI,
            custom: AIProvider.CUSTOM,
        };
        return providerMap[envValue.toLowerCase()] || defaultValue;
    };

    return {
        fast: {
            provider: parseProvider(process.env.AIOS_FAST_PROVIDER, AIProvider.OPENAI),
            model: process.env.AIOS_FAST_MODEL || 'gpt-4o-mini',
            apiKey: process.env.AIOS_FAST_API_KEY || process.env.OPENAI_API_KEY || '',
        },
        vision: {
            provider: parseProvider(process.env.AIOS_VISION_PROVIDER, AIProvider.GOOGLE),
            model: process.env.AIOS_VISION_MODEL || 'gemini-2.0-flash',
            apiKey: process.env.AIOS_VISION_API_KEY || process.env.GOOGLE_API_KEY || '',
        },
        smart: {
            provider: parseProvider(process.env.AIOS_SMART_PROVIDER, AIProvider.ANTHROPIC),
            model: process.env.AIOS_SMART_MODEL || 'claude-sonnet-4-20250514',
            apiKey: process.env.AIOS_SMART_API_KEY || process.env.ANTHROPIC_API_KEY || '',
        },
    };
}

async function main() {
    console.error('[AIOS Daemon] Starting...');

    // 注册适配器
    adapterRegistry.register(audioAdapter);
    adapterRegistry.register(displayAdapter);
    adapterRegistry.register(desktopAdapter);
    adapterRegistry.register(powerAdapter);
    adapterRegistry.register(appsAdapter);
    adapterRegistry.register(systemInfoAdapter);
    adapterRegistry.register(fileAdapter);
    adapterRegistry.register(windowAdapter);
    adapterRegistry.register(browserAdapter);
    adapterRegistry.register(speechAdapter);
    adapterRegistry.register(notificationAdapter);
    adapterRegistry.register(timerAdapter);
    adapterRegistry.register(calculatorAdapter);
    adapterRegistry.register(calendarAdapter);
    adapterRegistry.register(weatherAdapter);
    adapterRegistry.register(translateAdapter);

    // 初始化所有适配器
    await adapterRegistry.initializeAll();
    console.error(`[AIOS Daemon] Registered ${adapterRegistry.getAll().length} adapters`);

    // 创建 AI 路由器
    let aiRouter: AIRouter | null = null;
    let orchestrator: TaskOrchestrator | null = null;
    const aiConfig = getDefaultAIConfig();
    if (aiConfig.fast.apiKey || aiConfig.vision.apiKey || aiConfig.smart.apiKey) {
        try {
            aiRouter = new AIRouter({ config: aiConfig });
            console.error('[AIOS Daemon] AI Router initialized');

            // 创建任务编排器 (三层 AI 协调)
            const engines = (aiRouter as any).engines;
            if (engines) {
                orchestrator = new TaskOrchestrator({
                    fastEngine: engines.fast,
                    visionEngine: engines.vision,
                    smartEngine: engines.smart,
                    adapterRegistry,
                });
                console.error('[AIOS Daemon] TaskOrchestrator initialized');
            }
        } catch (error) {
            console.error('[AIOS Daemon] AI Router failed to initialize:', error);
        }
    }

    // 创建 JSON-RPC 处理器
    const handler = new JSONRPCHandler();

    // 注册系统方法
    handler.registerMethod('ping', async () => ({ pong: true, timestamp: Date.now() }));

    handler.registerMethod('getVersion', async () => ({ version: '0.1.0' }));

    handler.registerMethod('getAdapters', async () => {
        return adapterRegistry.getAll().map((a) => ({
            id: a.id,
            name: a.name,
            description: a.description,
            capabilities: a.capabilities,
        }));
    });

    // 注册适配器调用方法
    handler.registerMethod('invoke', async (params) => {
        const { adapterId, capability, args } = params as {
            adapterId: string;
            capability: string;
            args: Record<string, unknown>;
        };

        const adapter = adapterRegistry.get(adapterId);
        if (!adapter) {
            throw new Error(`Adapter not found: ${adapterId}`);
        }

        return adapter.invoke(capability, args || {});
    });

    // 获取适配器可用状态
    handler.registerMethod('getAdapterStatus', async (params) => {
        const { adapterId } = params as { adapterId: string };
        const adapter = adapterRegistry.get(adapterId);
        if (!adapter) {
            throw new Error(`Adapter not found: ${adapterId}`);
        }
        return {
            id: adapter.id,
            available: await adapter.checkAvailability(),
        };
    });

    // 获取所有适配器及其可用状态
    handler.registerMethod('getAdaptersWithStatus', async () => {
        const adapters = adapterRegistry.getAll();
        const results = await Promise.all(
            adapters.map(async (a) => ({
                id: a.id,
                name: a.name,
                description: a.description,
                capabilities: a.capabilities,
                available: await a.checkAvailability(),
            }))
        );
        return results;
    });

    // 注册 AI 聊天方法 (基础路由)
    handler.registerMethod('chat', async (params) => {
        if (!aiRouter) {
            throw new Error('AI Router not configured. Set API keys via environment variables.');
        }

        const { messages, options } = params as {
            messages: Array<{ role: string; content: string }>;
            options?: Record<string, unknown>;
        };

        return aiRouter.chat(messages as any, options as any);
    });

    // 注册智能聊天方法 (三层 AI 协调)
    handler.registerMethod('smartChat', async (params) => {
        if (!orchestrator) {
            throw new Error('TaskOrchestrator not configured. Set API keys via environment variables.');
        }

        const { message, hasScreenshot } = params as {
            message: string;
            hasScreenshot?: boolean;
        };

        const result = await orchestrator.process(message, { hasScreenshot });

        return {
            success: result.success,
            response: result.response,
            tier: result.tier,
            executionTime: result.executionTime,
            model: result.model,
        };
    });

    // 注册带工具的聊天方法
    handler.registerMethod('chatWithTools', async (params) => {
        if (!aiRouter) {
            throw new Error('AI Router not configured.');
        }

        const { messages, tools, options } = params as {
            messages: Array<{ role: string; content: string }>;
            tools: any[];
            options?: Record<string, unknown>;
        };

        return aiRouter.chatWithTools(messages as any, tools, options as any);
    });

    // 获取 AI 配置
    handler.registerMethod('getAIConfig', async () => {
        return {
            fast: {
                baseUrl: (aiConfig.fast as any).baseUrl || DEFAULT_URLS.openai,
                model: aiConfig.fast.model,
                apiKey: aiConfig.fast.apiKey ? '••••••••' : '',
            },
            vision: {
                baseUrl: (aiConfig.vision as any).baseUrl || DEFAULT_URLS.google,
                model: aiConfig.vision.model,
                apiKey: aiConfig.vision.apiKey ? '••••••••' : '',
            },
            smart: {
                baseUrl: (aiConfig.smart as any).baseUrl || DEFAULT_URLS.anthropic,
                model: aiConfig.smart.model,
                apiKey: aiConfig.smart.apiKey ? '••••••••' : '',
            },
        };
    });

    // 设置 AI 配置
    handler.registerMethod('setAIConfig', async (params) => {
        const { fast, vision, smart } = params as {
            fast?: { baseUrl: string; model: string; apiKey?: string };
            vision?: { baseUrl: string; model: string; apiKey?: string };
            smart?: { baseUrl: string; model: string; apiKey?: string };
        };

        // 构建新配置 - 从 baseUrl 推断 provider
        const inferProvider = (baseUrl: string): AIProvider => {
            if (baseUrl.includes('anthropic')) return AIProvider.ANTHROPIC;
            if (baseUrl.includes('google') || baseUrl.includes('generativelanguage')) return AIProvider.GOOGLE;
            if (baseUrl.includes('deepseek')) return AIProvider.DEEPSEEK;
            if (baseUrl.includes('groq')) return AIProvider.GROQ;
            return AIProvider.OPENAI; // 默认使用 OpenAI 兼容
        };

        const newConfig: AIRouterConfig = {
            fast: fast ? {
                provider: inferProvider(fast.baseUrl),
                model: fast.model,
                apiKey: fast.apiKey || aiConfig.fast.apiKey,
                baseURL: fast.baseUrl,
            } : aiConfig.fast,
            vision: vision ? {
                provider: inferProvider(vision.baseUrl),
                model: vision.model,
                apiKey: vision.apiKey || aiConfig.vision.apiKey,
                baseURL: vision.baseUrl,
            } : aiConfig.vision,
            smart: smart ? {
                provider: inferProvider(smart.baseUrl),
                model: smart.model,
                apiKey: smart.apiKey || aiConfig.smart.apiKey,
                baseURL: smart.baseUrl,
            } : aiConfig.smart,
        };

        try {
            aiRouter = new AIRouter({ config: newConfig });
            // 更新存储的配置
            Object.assign(aiConfig, newConfig);
            console.error('[AIOS Daemon] AI config updated');
            return { success: true };
        } catch (error) {
            throw new Error(`Failed to update AI config: ${error}`);
        }
    });

    // 获取模型列表 (OpenAI 兼容接口)
    handler.registerMethod('fetchModels', async (params) => {
        const { baseUrl, apiKey } = params as { baseUrl: string; apiKey?: string };

        try {
            // 标准化 URL
            let url = baseUrl.replace(/\/$/, '');
            if (!url.endsWith('/models')) {
                url = `${url}/models`;
            }

            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (apiKey) {
                headers['Authorization'] = `Bearer ${apiKey}`;
            }

            const response = await fetch(url, { headers });

            if (!response.ok) {
                const errorText = await response.text();
                return { success: false, error: `HTTP ${response.status}: ${errorText.substring(0, 200)}` };
            }

            const data = await response.json() as Record<string, unknown>;

            // OpenAI 格式: { data: [{ id, ... }] }
            // 有些服务直接返回数组
            let models: Array<{ id: string; name?: string; created?: number }> = [];
            const rawModels = Array.isArray(data) ? data : ((data.data || data.models || []) as unknown[]);

            // 标准化模型信息
            models = rawModels.map((m: unknown) => {
                const model = m as Record<string, unknown>;
                return {
                    id: (model.id || model.name || model.model) as string,
                    name: (model.name || model.id) as string,
                    created: model.created as number | undefined,
                };
            });

            // 按名称排序
            models.sort((a, b) => (a.id || '').localeCompare(b.id || ''));

            return { success: true, models };
        } catch (error: unknown) {
            const err = error as Error;
            return { success: false, error: err.message || '获取模型列表失败' };
        }
    });

    // 测试 AI 连接
    handler.registerMethod('testAIConnection', async (params) => {
        const { baseUrl, apiKey, model } = params as { baseUrl: string; apiKey?: string; model: string };

        try {
            // 标准化 URL
            let url = baseUrl.replace(/\/$/, '');
            if (!url.endsWith('/chat/completions')) {
                url = `${url}/chat/completions`;
            }

            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (apiKey) {
                headers['Authorization'] = `Bearer ${apiKey}`;
            }

            const body = {
                model,
                messages: [{ role: 'user', content: 'Say "Hello" in one word.' }],
                max_tokens: 10,
            };

            const response = await fetch(url, {
                method: 'POST',
                headers,
                body: JSON.stringify(body),
            });

            if (!response.ok) {
                const errorText = await response.text();
                return { success: false, error: `HTTP ${response.status}: ${errorText.substring(0, 200)}` };
            }

            const data = await response.json() as Record<string, unknown>;
            const choices = data.choices as Array<{ message?: { content?: string } }> | undefined;
            const content = choices?.[0]?.message?.content || (data.content as string) || JSON.stringify(data).substring(0, 100);

            return { success: true, response: content };
        } catch (error: unknown) {
            const err = error as Error;
            return { success: false, error: err.message || '连接测试失败' };
        }
    });

    // 启动 stdio 传输
    const transport = new StdioTransport(handler);
    transport.start();

    // 可选: 启动 WebSocket 传输
    const wsPort = process.env.AIOS_WEBSOCKET_PORT;
    let wsTransport: WebSocketTransport | null = null;
    if (wsPort) {
        wsTransport = new WebSocketTransport({ port: parseInt(wsPort, 10) });
        wsTransport.setMessageHandler(async (request) => handler.handleRequest(request));
        await wsTransport.start();
        console.error(`[AIOS Daemon] WebSocket server started on port ${wsPort}`);
    }


    console.error('[AIOS Daemon] Ready');

    // 优雅关闭
    process.on('SIGINT', async () => {
        console.error('[AIOS Daemon] Shutting down...');
        if (wsTransport) {
            await wsTransport.stop();
        }
        await adapterRegistry.shutdownAll();
        process.exit(0);
    });
}

main().catch((error) => {
    console.error('[AIOS Daemon] Fatal error:', error);
    process.exit(1);
});
