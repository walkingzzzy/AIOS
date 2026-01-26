/**
 * AIOS Daemon 主入口
 */

import type { AIRouterConfig } from '@aios/shared';
import { AIProvider } from '@aios/shared';
import { AIRouter } from './ai/index.js';
import { SkillRegistry, ProjectMemoryManager } from './core/skills/index.js';
import { OAuthManager, getOAuthConfig, OAuthEnvVars } from './auth/index.js';
import { MCPServer, MCPServerV2, A2AServer, type AgentCard } from './protocol/index.js';
import {
    adapterRegistry,
    JSONRPCHandler,
    StdioTransport,
    WebSocketTransport,
    TaskOrchestrator,
    ToolExecutor,
    TaskScheduler,
    SessionManager,
    confirmationManager,
    permissionManager,
    HookManager,
    LoggingHook,
    MetricsHook,
    ToolTraceRepository,
    ToolTraceHook,
    UsageRepository,
    UsageHook,
    traceContextManager,
    EventStream,
    EventType,
    setEventStream,
    HealthCheckService,
} from './core/index.js';
import { Storage } from './core/Storage.js';
import { TaskAPI } from './api/TaskAPI.js';
import {
    audioAdapter,
    displayAdapter,
    desktopAdapter,
    powerAdapter,
    networkAdapter,
    focusModeAdapter,
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
    screenshotAdapter,
    clipboardAdapter,
    officeLocalAdapter,
    // 新增适配器
    SpotifyAdapter,
    SlackAdapter,
    DiscordAdapter,
    GmailAdapter,
    OutlookAdapter,
    GoogleWorkspaceAdapter,
    NotionAdapter,
    Microsoft365Adapter,
    qqntAdapter,
    wpsAirScriptAdapter,
    feishuAdapter,
    capcutDraftAdapter,
    wechatOcrAdapter,
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

// AI 配置持久化键名
const AI_CONFIG_STORAGE_KEY = 'ai_config';
const DAEMON_VERSION = '0.1.0';

/**
 * 从 Storage 加载保存的 AI 配置，与默认配置合并
 */
function loadSavedAIConfig(storage: import('./core/Storage.js').Storage): AIRouterConfig {
    const defaults = getDefaultAIConfig();

    try {
        const saved = storage.getJSON<Partial<AIRouterConfig>>(AI_CONFIG_STORAGE_KEY);
        if (saved) {
            console.error('[AIOS Daemon] Loading saved AI config from storage');
            return {
                fast: saved.fast ? { ...defaults.fast, ...saved.fast } : defaults.fast,
                vision: saved.vision ? { ...defaults.vision, ...saved.vision } : defaults.vision,
                smart: saved.smart ? { ...defaults.smart, ...saved.smart } : defaults.smart,
            };
        }
    } catch (error) {
        console.error('[AIOS Daemon] Failed to load saved AI config:', error);
    }

    return defaults;
}

/**
 * 保存 AI 配置到 Storage
 */
function saveAIConfig(storage: import('./core/Storage.js').Storage, config: AIRouterConfig): void {
    try {
        // 保存时不存储敏感的完整 API Key，只保存必要的配置
        storage.setJSON(AI_CONFIG_STORAGE_KEY, config);
        console.error('[AIOS Daemon] AI config saved to storage');
    } catch (error) {
        console.error('[AIOS Daemon] Failed to save AI config:', error);
    }
}

async function main() {
    const daemonStartedAt = Date.now();
    const wsPort = process.env.AIOS_WEBSOCKET_PORT;
    const mcpPort = process.env.AIOS_MCP_PORT;
    const useMcpV2 = process.env.AIOS_MCP_USE_V2 === '1';
    const a2aPort = process.env.AIOS_A2A_PORT;
    // Keep stdout clean for JSON-RPC responses over stdio.
    console.log = console.error;
    console.info = console.error;
    console.debug = console.error;

    console.error('[AIOS Daemon] Starting...');

    // 初始化存储（KV + 会话/任务持久化）
    const storage = new Storage();
    const sessionManager = new SessionManager(storage.getDatabase());

    // ============ Trace / Hooks / Audit / Usage ============
    const sampleRateEnv = Number(process.env.AIOS_TRACE_SAMPLE_RATE);
    if (Number.isFinite(sampleRateEnv)) {
        traceContextManager.setSampleRate(sampleRateEnv);
    }

    const hookManager = new HookManager({
        enabled: process.env.AIOS_HOOKS_ENABLED !== '0',
    });

    hookManager.register(new LoggingHook({
        logLevel: (process.env.AIOS_HOOK_LOG_LEVEL as 'debug' | 'info' | 'warn' | 'error') || 'info',
    }));
    hookManager.register(new MetricsHook());

    const toolTraceRepository = new ToolTraceRepository();
    hookManager.register(new ToolTraceHook(toolTraceRepository));

    const usageRepository = new UsageRepository();
    hookManager.register(new UsageHook(usageRepository));

    const mcpToolExecutor = new ToolExecutor(adapterRegistry);
    mcpToolExecutor.setHookManager(hookManager);

    // ============ 统一事件流系统 ============
    const eventStream = new EventStream({
        maxEvents: 10000,
        eventTTL: 3600000, // 1 hour
        enablePersistence: false,
    });
    setEventStream(eventStream);
    console.error('[AIOS Daemon] EventStream initialized');

    // 注册 EventBridgeHook - 将 Hook 事件桥接到 EventStream
    const { EventBridgeHook } = await import('./core/hooks/EventBridgeHook.js');
    hookManager.register(new EventBridgeHook(eventStream, {
        bridgeTaskEvents: true,
        bridgeLLMEvents: true,
        bridgeToolEvents: true,
        bridgeProgressEvents: true,
    }));
    console.error('[AIOS Daemon] EventBridgeHook registered');

    // ============ OAuth / Token 配置 ============
    const oauthManager = new OAuthManager(storage);
    const oauthRedirectUri = process.env.AIOS_OAUTH_REDIRECT_URI;

    for (const [providerId, env] of Object.entries(OAuthEnvVars)) {
        const clientId = process.env[env.clientId];
        const clientSecret = process.env[env.clientSecret];
        if (clientId && clientSecret) {
            oauthManager.registerProvider(
                providerId,
                getOAuthConfig(providerId, clientId, clientSecret, oauthRedirectUri)
            );
        }
    }

    // 注册适配器
    adapterRegistry.register(audioAdapter);
    adapterRegistry.register(displayAdapter);
    adapterRegistry.register(desktopAdapter);
    adapterRegistry.register(powerAdapter);
    adapterRegistry.register(networkAdapter);
    adapterRegistry.register(focusModeAdapter);
    adapterRegistry.register(appsAdapter);
    adapterRegistry.register(systemInfoAdapter);
    adapterRegistry.register(fileAdapter);
    adapterRegistry.register(windowAdapter);
    adapterRegistry.register(browserAdapter);
    adapterRegistry.register(officeLocalAdapter);
    adapterRegistry.register(speechAdapter);
    adapterRegistry.register(notificationAdapter);
    adapterRegistry.register(timerAdapter);
    adapterRegistry.register(calculatorAdapter);
    adapterRegistry.register(calendarAdapter);
    adapterRegistry.register(weatherAdapter);
    adapterRegistry.register(translateAdapter);
    adapterRegistry.register(screenshotAdapter);
    adapterRegistry.register(clipboardAdapter);
    adapterRegistry.register(qqntAdapter);
    adapterRegistry.register(wpsAirScriptAdapter);
    adapterRegistry.register(feishuAdapter);
    adapterRegistry.register(capcutDraftAdapter);
    adapterRegistry.register(wechatOcrAdapter);

    // 注册新增适配器（需要 OAuth 配置后才可用）
    const spotifyAdapter = new SpotifyAdapter();
    const slackAdapter = new SlackAdapter();
    const discordAdapter = new DiscordAdapter();
    const gmailAdapter = new GmailAdapter();
    const outlookAdapter = new OutlookAdapter();
    const googleWorkspaceAdapter = new GoogleWorkspaceAdapter();
    const notionAdapter = new NotionAdapter();
    const microsoft365Adapter = new Microsoft365Adapter();

    spotifyAdapter.setOAuthManager(oauthManager);
    gmailAdapter.setOAuthManager(oauthManager);
    outlookAdapter.setOAuthManager(oauthManager);
    googleWorkspaceAdapter.setOAuthManager(oauthManager);
    microsoft365Adapter.setOAuthManager(oauthManager);
    calendarAdapter.setOAuthManager(oauthManager);

    if (process.env.SLACK_BOT_TOKEN) {
        slackAdapter.setToken(process.env.SLACK_BOT_TOKEN);
    }
    if (process.env.DISCORD_BOT_TOKEN) {
        discordAdapter.setToken(process.env.DISCORD_BOT_TOKEN);
    }
    const notionToken = process.env.NOTION_TOKEN || process.env.NOTION_API_TOKEN;
    if (notionToken) {
        notionAdapter.setToken(notionToken);
    }

    adapterRegistry.register(spotifyAdapter);
    adapterRegistry.register(slackAdapter);
    adapterRegistry.register(discordAdapter);
    adapterRegistry.register(gmailAdapter);
    adapterRegistry.register(outlookAdapter);
    adapterRegistry.register(googleWorkspaceAdapter);
    adapterRegistry.register(notionAdapter);
    adapterRegistry.register(microsoft365Adapter);

    // 初始化所有适配器
    await adapterRegistry.initializeAll();
    console.error(`[AIOS Daemon] Registered ${adapterRegistry.getAll().length} adapters`);

    // 创建 Skills 系统
    const skillRegistry = new SkillRegistry({
        userSkillsDir: `${process.env.HOME}/.aios/skills`,
        projectSkillsDir: '.aios/skills',
        autoDiscover: true,
    });
    const projectMemoryManager = new ProjectMemoryManager();
    console.error(`[AIOS Daemon] SkillRegistry initialized with ${skillRegistry.count} skills`);

    // 创建 AI 路由器
    let aiRouter: AIRouter | null = null;
    let orchestrator: TaskOrchestrator | null = null;
    let wsTransport: WebSocketTransport | null = null;
    let mcpServer: MCPServer | MCPServerV2 | null = null;
    let a2aServer: A2AServer | null = null;
    const a2aTaskIdByAiosTaskId = new Map<string, string>();

    const emitNotification = (method: string, params: unknown): void => {
        try {
            process.stdout.write(JSON.stringify({ jsonrpc: '2.0', method, params }) + '\n');
        } catch {
            // ignore
        }
        wsTransport?.broadcast(method, params);
    };
    eventStream.subscribe((event) => {
        emitNotification('events:emit', event);
    });
    confirmationManager.setNotifier((request) => {
        emitNotification('confirmation:request', request);
    });

    // 任务调度器（用于 task.* API）
    const concurrencyEnv = Number(process.env.AIOS_TASK_CONCURRENCY);
    const scheduler = new TaskScheduler(async (task) => {
        // 运行状态（持久化）
        sessionManager.updateTaskStatus(task.id, 'running');

        if (!orchestrator) {
            const message = 'TaskOrchestrator not configured. Set API keys via environment variables.';
            sessionManager.updateTaskStatus(task.id, 'failed', { error: message });
            throw new Error(message);
        }

        try {
            const sessionId = typeof task.context?.sessionId === 'string' ? task.context.sessionId : undefined;
            const result = await orchestrator.process(task.prompt, {
                hasScreenshot: false,
                taskId: task.id,
                sessionId,
            });
            sessionManager.updateTaskStatus(task.id, result.success ? 'completed' : 'failed', {
                response: result.response,
                tier: result.tier,
                model: result.model,
                executionTime: result.executionTime,
                error: result.success ? undefined : result.response,
            });
            return result;
        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            sessionManager.updateTaskStatus(task.id, 'failed', { error: message });
            throw error;
        }
    }, {
        concurrency: Number.isFinite(concurrencyEnv) && concurrencyEnv > 0 ? concurrencyEnv : 1,
    });
    const schedulerCleanupTimer = setInterval(() => {
        scheduler.cleanup();
    }, 10 * 60 * 1000);
    schedulerCleanupTimer.unref?.();

    // 推送任务事件到客户端（用于渲染进程监听）
    scheduler.on('task:started', (...args: unknown[]) => {
        const task = args[0] as { id: string; prompt?: string };

        // 发送 task:progress 事件
        emitNotification('task:progress', {
            taskId: task.id,
            percentage: 0,
            currentStep: 0,
            totalSteps: 1,
            stepDescription: '开始执行',
        });

        // 发送 task:update 事件（用于 TaskBoard）
        emitNotification('task:update', {
            type: 'task_created',
            taskId: task.id,
            task: {
                id: task.id,
                title: (task.prompt || '执行任务').substring(0, 50),
                status: 'running',
                subTasks: [{
                    id: `${task.id}_main`,
                    description: '正在处理...',
                    status: 'running',
                }],
                createdAt: Date.now(),
            }
        });

        const a2aTaskId = a2aTaskIdByAiosTaskId.get(task.id);
        if (a2aTaskId && a2aServer) {
            a2aServer.updateTaskStatus(a2aTaskId, 'processing');
        }
    });

    scheduler.on('task:completed', (...args: unknown[]) => {
        const task = args[0] as { id: string; result?: unknown };
        const result = task.result as any;
        emitNotification('task:progress', {
            taskId: task.id,
            percentage: 100,
            currentStep: 1,
            totalSteps: 1,
            stepDescription: '已完成',
        });
        emitNotification('task:complete', {
            taskId: task.id,
            success: true,
            response: result?.response ?? '',
            executionTime: result?.executionTime ?? 0,
        });

        // 更新 TaskBoard 状态
        emitNotification('task:update', {
            type: 'task_status',
            taskId: task.id,
            status: 'completed',
        });

        const a2aTaskId = a2aTaskIdByAiosTaskId.get(task.id);
        if (a2aTaskId && a2aServer) {
            a2aServer.updateTaskStatus(a2aTaskId, 'completed', result);
            a2aTaskIdByAiosTaskId.delete(task.id);
        }
    });

    scheduler.on('task:failed', (...args: unknown[]) => {
        const task = args[0] as { id: string };
        const error = args[1];
        const message = error instanceof Error ? error.message : String(error);
        emitNotification('task:error', {
            taskId: task.id,
            error: message,
            recoverable: false,
        });

        // 更新 TaskBoard 状态
        emitNotification('task:update', {
            type: 'task_status',
            taskId: task.id,
            status: 'failed',
        });

        const a2aTaskId = a2aTaskIdByAiosTaskId.get(task.id);
        if (a2aTaskId && a2aServer) {
            a2aServer.updateTaskStatus(a2aTaskId, 'failed', undefined, message);
            a2aTaskIdByAiosTaskId.delete(task.id);
        }
    });

    const taskAPI = new TaskAPI(scheduler, sessionManager);
    const aiConfig = loadSavedAIConfig(storage);
    if (aiConfig.fast.apiKey || aiConfig.vision.apiKey || aiConfig.smart.apiKey) {
        try {
            aiRouter = new AIRouter({ config: aiConfig });
            console.error('[AIOS Daemon] AI Router initialized');

            // 打印三层AI引擎配置信息
            const engines = (aiRouter as any).engines;
            if (engines) {
                console.error('[AIOS] AI引擎配置:');

                // Fast层配置
                const fastConfig = engines.fast.getConfigInfo();
                console.error(`  Fast层 (${fastConfig.model}):`);
                console.error(`    - 模型: ${fastConfig.model}`);
                console.error(`    - API地址: ${fastConfig.apiUrl}`);
                console.error(`    - 状态: ${fastConfig.isConfigured ? '✓ 已配置' : '✗ 未配置'}`);

                // Vision层配置
                const visionConfig = engines.vision.getConfigInfo();
                console.error(`  Vision层 (${visionConfig.model}):`);
                console.error(`    - 模型: ${visionConfig.model}`);
                console.error(`    - API地址: ${visionConfig.apiUrl}`);
                console.error(`    - 状态: ${visionConfig.isConfigured ? '✓ 已配置' : '✗ 未配置'}`);

                // Smart层配置
                const smartConfig = engines.smart.getConfigInfo();
                console.error(`  Smart层 (${smartConfig.model}):`);
                console.error(`    - 模型: ${smartConfig.model}`);
                console.error(`    - API地址: ${smartConfig.apiUrl}`);
                console.error(`    - 状态: ${smartConfig.isConfigured ? '✓ 已配置' : '✗ 未配置'}`);

                // 创建任务编排器 (三层 AI 协调)
                orchestrator = new TaskOrchestrator({
                    fastEngine: engines.fast,
                    visionEngine: engines.vision,
                    smartEngine: engines.smart,
                    adapterRegistry,
                    hookManager,
                    // Skills 系统配置
                    skillRegistry,
                    projectMemoryManager,
                    enableSkills: true,
                    // Phase 6: ReAct 循环 (复杂任务推理)
                    enableReAct: process.env.AIOS_ENABLE_REACT !== '0',
                    // Phase 8: O-W 模式 (并行任务分解)
                    enableOrchestratorWorker: process.env.AIOS_ENABLE_OW !== '0',
                    maxWorkers: 5,
                    // Phase 8: 高危操作确认
                    confirmationManager,
                    enableConfirmation: process.env.AIOS_ENABLE_CONFIRMATION !== '0',
                    // Phase 9: 计划确认流程（复杂任务执行前需用户确认）
                    enablePlanConfirmation: process.env.AIOS_ENABLE_PLAN_CONFIRMATION !== '0',
                    planConfirmationTimeout: 5 * 60 * 1000, // 5 分钟
                });
                console.error('[AIOS Daemon] TaskOrchestrator initialized (ReAct + O-W + Confirmation + PlanConfirmation enabled)');
            }
        } catch (error) {
            console.error('[AIOS Daemon] AI Router failed to initialize:', error);
        }
    }

    // 创建 JSON-RPC 处理器
    const handler = new JSONRPCHandler();

    // 注册系统方法
    handler.registerMethod('ping', async () => ({ pong: true, timestamp: Date.now() }));

    handler.registerMethod('getVersion', async () => ({ version: DAEMON_VERSION }));

    const healthCheckService = new HealthCheckService({
        adapterRegistry,
        version: DAEMON_VERSION,
        startedAt: daemonStartedAt,
        transportProvider: () => ({
            stdio: { enabled: true },
            websocket: {
                enabled: !!wsTransport,
                port: wsPort ? parseInt(wsPort, 10) : undefined,
                clients: wsTransport?.getClientCount(),
            },
            mcp: {
                enabled: !!mcpServer,
                mode: useMcpV2 ? 'v2' : 'v1',
                port: mcpPort ? parseInt(mcpPort, 10) : undefined,
                host: process.env.AIOS_MCP_HOST ?? '127.0.0.1',
            },
            a2a: {
                enabled: !!a2aServer,
                port: a2aPort ? parseInt(a2aPort, 10) : undefined,
                host: process.env.AIOS_A2A_HOST ?? '127.0.0.1',
            },
        }),
    });

    handler.registerMethod('health.check', async () => healthCheckService.check());

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

        // 查找能力定义
        const capabilityDef = adapter.capabilities.find(c => c.id === capability);
        if (!capabilityDef) {
            throw new Error(`Capability not found: ${capability}`);
        }

        // 权限检查
        if (capabilityDef.permissionLevel !== 'public') {
            const permCheck = await permissionManager.checkPermission(capabilityDef.permissionLevel);
            if (!permCheck.granted) {
                throw new Error(`Permission denied: ${capabilityDef.permissionLevel} level required. ${permCheck.details || ''}`);
            }
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

    // 权限检查
    handler.registerMethod('checkPermission', async (params) => {
        const { level } = params as { level: 'public' | 'low' | 'medium' | 'high' | 'critical' };
        return permissionManager.checkPermission(level);
    });

    // 请求权限
    handler.registerMethod('requestPermission', async (params) => {
        const { level } = params as { level: 'public' | 'low' | 'medium' | 'high' | 'critical' };
        return permissionManager.requestPermission(level);
    });

    // ============ Task / Confirmation API ============

    // 注册 Task API
    taskAPI.registerMethods(handler);

    // 确认响应（用于高风险操作）
    handler.registerMethod('confirmation.respond', async (params) => {
        const { requestId, confirmed, reason } = params as {
            requestId: string;
            confirmed: boolean;
            reason?: string;
        };
        const ok = confirmationManager.respond(requestId, confirmed, reason);
        return { success: ok };
    });

    // ============ Plan Approval API ============

    // 获取待审批计划
    handler.registerMethod('plan.getPending', async (params) => {
        const { taskId } = params as { taskId: string };
        if (!orchestrator) {
            return null;
        }
        // 通过 orchestrator 访问 planConfirmationManager
        const manager = (orchestrator as any).planConfirmationManager;
        if (!manager) {
            return null;
        }
        return manager.getPendingPlan(taskId) || null;
    });

    // 确认计划
    handler.registerMethod('plan.approve', async (params) => {
        const { draftId, modifications } = params as {
            draftId: string;
            modifications?: unknown[];
        };
        if (!orchestrator) {
            return { success: false, message: 'Orchestrator not initialized' };
        }
        const manager = (orchestrator as any).planConfirmationManager;
        if (!manager) {
            return { success: false, message: 'PlanConfirmationManager not available' };
        }
        try {
            manager.handleApprovalResponse(draftId, {
                approved: true,
                modifiedSteps: modifications as any,
            });
            return { success: true };
        } catch (error) {
            return { success: false, message: error instanceof Error ? error.message : String(error) };
        }
    });

    // 拒绝计划
    handler.registerMethod('plan.reject', async (params) => {
        const { draftId, feedback } = params as {
            draftId: string;
            feedback?: string;
        };
        if (!orchestrator) {
            return { success: false, message: 'Orchestrator not initialized' };
        }
        const manager = (orchestrator as any).planConfirmationManager;
        if (!manager) {
            return { success: false, message: 'PlanConfirmationManager not available' };
        }
        try {
            manager.handleApprovalResponse(draftId, {
                approved: false,
                feedback,
            });
            return { success: true };
        } catch (error) {
            return { success: false, message: error instanceof Error ? error.message : String(error) };
        }
    });

    // 修改计划
    handler.registerMethod('plan.modify', async (params) => {
        const { draftId, modifications } = params as {
            draftId: string;
            modifications: unknown;
        };
        if (!orchestrator) {
            return { success: false, message: 'Orchestrator not initialized' };
        }
        const manager = (orchestrator as any).planConfirmationManager;
        if (!manager) {
            return { success: false, message: 'PlanConfirmationManager not available' };
        }
        try {
            const updatedPlan = manager.updatePlan(draftId, modifications);
            if (updatedPlan) {
                // 发送修改事件到前端
                emitNotification('plan:modified', updatedPlan);
                return { success: true, plan: updatedPlan };
            }
            return { success: false, message: 'Draft not found' };
        } catch (error) {
            return { success: false, message: error instanceof Error ? error.message : String(error) };
        }
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

        const { message, hasScreenshot, sessionId } = params as {
            message: string;
            hasScreenshot?: boolean;
            sessionId?: string;
        };

        const result = await orchestrator.process(message, { hasScreenshot, sessionId });

        return {
            success: result.success,
            response: result.response,
            tier: result.tier,
            executionTime: result.executionTime,
            model: result.model,
        };
    });

    // ============ 流式智能对话 ============

    // 正在进行的流式任务
    const activeStreamTasks = new Map<string, AbortController>();

    // 流式智能聊天
    handler.registerMethod('smartChatStream', async (params) => {
        if (!orchestrator) {
            throw new Error('TaskOrchestrator not configured. Set API keys via environment variables.');
        }

        const { message, hasScreenshot, sessionId } = params as {
            message: string;
            hasScreenshot?: boolean;
            sessionId?: string;
        };

        const taskId = `stream_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
        const abortController = new AbortController();
        activeStreamTasks.set(taskId, abortController);

        // 异步执行流式处理
        (async () => {
            const startTime = Date.now();
            try {
                const stream = orchestrator!.processStream(message, {
                    hasScreenshot,
                    taskId,
                    sessionId,
                    abortSignal: abortController.signal,
                });

                let fullContent = '';

                for await (const chunk of stream) {
                    if (abortController.signal.aborted) {
                        break;
                    }

                    // 发送流式块事件
                    emitNotification('task:stream-chunk', {
                        taskId,
                        content: chunk.content,
                        reasoningContent: chunk.reasoningContent,
                        toolCalls: chunk.toolCalls,
                        finishReason: chunk.finishReason,
                        usage: chunk.usage,
                    });

                    if (chunk.content) {
                        fullContent += chunk.content;
                    }
                }

                // 发送完成事件
                emitNotification('task:stream-complete', {
                    taskId,
                    success: true,
                    response: fullContent,
                    executionTime: Date.now() - startTime,
                    tier: 'fast',  // 流式处理总是使用 Fast 层
                });
            } catch (error) {
                const errorMessage = error instanceof Error ? error.message : String(error);
                emitNotification('task:stream-complete', {
                    taskId,
                    success: false,
                    response: errorMessage,
                    executionTime: Date.now() - startTime,
                    tier: 'fast',
                });
            } finally {
                activeStreamTasks.delete(taskId);
            }
        })();

        // 立即返回 taskId
        return { taskId };
    });

    // 取消流式请求
    handler.registerMethod('cancelStream', async (params) => {
        const { taskId } = params as { taskId: string };
        const controller = activeStreamTasks.get(taskId);
        if (controller) {
            controller.abort();
            activeStreamTasks.delete(taskId);
            return { success: true };
        }
        return { success: false, message: 'Task not found' };
    });

    // ============ 事件流 API ============

    // 获取最近事件
    handler.registerMethod('events.getRecent', async (params) => {
        const { count } = params as { count?: number };
        return eventStream.getRecent(count ?? 100);
    });

    // 查询事件
    handler.registerMethod('events.query', async (params) => {
        const { filter } = params as {
            filter?: {
                types?: string[];
                taskId?: string;
                source?: string;
                startTime?: number;
                endTime?: number;
            };
        };

        // 转换类型字符串为 EventType 枚举
        const eventFilter = filter ? {
            ...filter,
            types: filter.types?.map(t => t as EventType),
        } : {};

        return eventStream.query(eventFilter);
    });

    // 按任务 ID 查询事件
    handler.registerMethod('events.queryByTask', async (params) => {
        const { taskId } = params as { taskId: string };
        return eventStream.queryByTask(taskId);
    });

    // 获取事件统计
    handler.registerMethod('events.getStats', async () => {
        return eventStream.getStats();
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
                baseUrl: (aiConfig.fast as any).baseURL || DEFAULT_URLS.openai,
                model: aiConfig.fast.model,
                apiKey: aiConfig.fast.apiKey ? '••••••••' : '',
            },
            vision: {
                baseUrl: (aiConfig.vision as any).baseURL || DEFAULT_URLS.google,
                model: aiConfig.vision.model,
                apiKey: aiConfig.vision.apiKey ? '••••••••' : '',
            },
            smart: {
                baseUrl: (aiConfig.smart as any).baseURL || DEFAULT_URLS.anthropic,
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
            // 持久化配置到 Storage
            saveAIConfig(storage, newConfig);
            // 重建 orchestrator 以使用新配置
            const engines = (aiRouter as any).engines;
            if (engines) {
                orchestrator = new TaskOrchestrator({
                    fastEngine: engines.fast,
                    visionEngine: engines.vision,
                    smartEngine: engines.smart,
                    adapterRegistry,
                    hookManager,
                    // Skills 系统配置
                    skillRegistry,
                    projectMemoryManager,
                    enableSkills: true,
                    // Phase 6: ReAct 循环
                    enableReAct: process.env.AIOS_ENABLE_REACT !== '0',
                    // Phase 8: O-W 模式
                    enableOrchestratorWorker: process.env.AIOS_ENABLE_OW !== '0',
                    maxWorkers: 5,
                    // Phase 8: 高危操作确认
                    confirmationManager,
                    enableConfirmation: process.env.AIOS_ENABLE_CONFIRMATION !== '0',
                });
            }
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

    // ============ MCP 配置 API ============

    // 初始化 MCP 服务器注册表
    const { getMCPServerRegistry } = await import('./core/MCPServerRegistry.js');
    const mcpServerRegistry = getMCPServerRegistry();
    await mcpServerRegistry.initialize();

    // 获取 MCP 服务器配置
    handler.registerMethod('mcp.getConfig', async () => {
        const mcpPort = process.env.AIOS_MCP_PORT;
        return {
            enabled: !!mcpServer,
            port: mcpPort ? parseInt(mcpPort, 10) : null,
            host: process.env.AIOS_MCP_HOST || '127.0.0.1',
        };
    });

    // 获取 MCP 服务器运行状态
    handler.registerMethod('mcp.getStatus', async () => {
        return {
            running: !!mcpServer,
            // TODO: 获取连接的客户端数量
            connectedClients: 0,
            exposedTools: adapterRegistry.getAll().flatMap(a =>
                a.capabilities.map(c => `${a.id}.${c.id}`)
            ),
        };
    });

    // 列出已配置的外部 MCP 服务器
    handler.registerMethod('mcp.listServers', async () => {
        return mcpServerRegistry.list();
    });

    // 添加外部 MCP 服务器
    handler.registerMethod('mcp.addServer', async (params) => {
        const { name, type, command, args, url } = params as {
            name: string;
            type: 'stdio' | 'websocket';
            command?: string;
            args?: string[];
            url?: string;
        };
        return mcpServerRegistry.add({ name, type, command, args, url });
    });

    // 移除外部 MCP 服务器
    handler.registerMethod('mcp.removeServer', async (params) => {
        const { name } = params as { name: string };
        return { success: await mcpServerRegistry.remove(name) };
    });

    // 测试 MCP 服务器连接
    handler.registerMethod('mcp.testConnection', async (params) => {
        const { name } = params as { name: string };
        return mcpServerRegistry.test(name);
    });

    // 连接 MCP 服务器
    handler.registerMethod('mcp.connect', async (params) => {
        const { name } = params as { name: string };
        try {
            await mcpServerRegistry.connect(name);
            return { success: true };
        } catch (error: any) {
            return { success: false, error: error.message };
        }
    });

    // 断开 MCP 服务器连接
    handler.registerMethod('mcp.disconnect', async (params) => {
        const { name } = params as { name: string };
        await mcpServerRegistry.disconnect(name);
        return { success: true };
    });

    // 获取所有外部 MCP 服务器提供的工具
    handler.registerMethod('mcp.getExternalTools', async () => {
        return mcpServerRegistry.getAllTools();
    });

    // ============ A2A 配置 API ============

    // 当前 Agent Card（可动态修改）
    let currentAgentCard: AgentCard = {
        id: process.env.AIOS_A2A_AGENT_ID ?? 'aios',
        name: process.env.AIOS_A2A_AGENT_NAME ?? 'AIOS',
        description: process.env.AIOS_A2A_AGENT_DESCRIPTION ?? 'AIOS Agent - Intelligent Operating System Assistant',
        capabilities: adapterRegistry.getAll().map((a) => a.id),
        endpoint: '',
    };

    // 获取 A2A 服务器配置
    handler.registerMethod('a2a.getConfig', async () => {
        const a2aPort = process.env.AIOS_A2A_PORT;
        return {
            enabled: !!a2aServer,
            port: a2aPort ? parseInt(a2aPort, 10) : null,
            host: process.env.AIOS_A2A_HOST || '127.0.0.1',
        };
    });

    // 获取 A2A 服务器运行状态
    handler.registerMethod('a2a.getStatus', async () => {
        return {
            running: !!a2aServer,
            // TODO: 跟踪已处理任务数量
            tasksProcessed: 0,
        };
    });

    // 获取 Agent Card
    handler.registerMethod('a2a.getAgentCard', async () => {
        return currentAgentCard;
    });

    // 设置 Agent Card（部分更新）
    handler.registerMethod('a2a.setAgentCard', async (params) => {
        const { id, name, description, capabilities } = params as Partial<AgentCard>;
        if (id) currentAgentCard.id = id;
        if (name) currentAgentCard.name = name;
        if (description) currentAgentCard.description = description;
        if (capabilities) currentAgentCard.capabilities = capabilities;

        // TODO: 持久化到存储
        console.error('[AIOS Daemon] Agent Card updated:', currentAgentCard);

        return { success: true, agentCard: currentAgentCard };
    });

    // 生成 A2A 访问 Token
    handler.registerMethod('a2a.generateToken', async (params) => {
        if (!a2aServer) {
            return { success: false, error: 'A2A server not running' };
        }
        const { clientId, skills } = params as { clientId: string; skills?: string[] };
        const token = a2aServer.generateToken(clientId, skills || currentAgentCard.capabilities);
        return { success: true, token };
    });

    // 启动 stdio 传输
    const transport = new StdioTransport(handler);
    transport.start();

    // 可选: 启动 WebSocket 传输
    if (wsPort) {
        const wsToken = process.env.AIOS_WEBSOCKET_TOKEN;
        if (!wsToken) {
            console.error('[AIOS Daemon] Refusing to start WebSocket server: AIOS_WEBSOCKET_TOKEN is required');
        } else {
            wsTransport = new WebSocketTransport({ port: parseInt(wsPort, 10), authToken: wsToken });
            wsTransport.setMessageHandler(async (request) => handler.handleRequest(request));
            await wsTransport.start();
            console.error(`[AIOS Daemon] WebSocket server started on port ${wsPort}`);
        }
    }

    // 可选: 启动 MCP WebSocket Server（工具暴露给 MCP 客户端）
    if (mcpPort) {
        const mcpToken = process.env.AIOS_MCP_TOKEN;
        const mcpHost = process.env.AIOS_MCP_HOST ?? '127.0.0.1';
        if (!mcpToken) {
            console.error('[AIOS Daemon] Refusing to start MCP server: AIOS_MCP_TOKEN is required');
        } else {
            if (useMcpV2) {
                mcpServer = new MCPServerV2(adapterRegistry, mcpToolExecutor);
                await mcpServer.start({
                    port: parseInt(mcpPort, 10),
                    host: mcpHost,
                    authToken: mcpToken,
                });
                console.error(
                    `[AIOS Daemon] MCPServerV2 started on ws://${mcpHost}:${mcpPort} (token via ?token=... or Authorization: Bearer ...)`
                );
            } else {
                mcpServer = new MCPServer(adapterRegistry, mcpToolExecutor);
                await mcpServer.start({
                    port: parseInt(mcpPort, 10),
                    host: mcpHost,
                    authToken: mcpToken,
                });
                console.error(
                    `[AIOS Daemon] MCP server started on ws://${mcpHost}:${mcpPort} (token via ?token=... or Authorization: Bearer ...)`
                );
            }
        }
    }

    // 可选: 启动 A2A HTTP Server（Agent Card + 任务接收）
    if (a2aPort) {
        const a2aTokenSecret = process.env.AIOS_A2A_TOKEN_SECRET;
        const a2aHost = process.env.AIOS_A2A_HOST ?? '127.0.0.1';
        if (!a2aTokenSecret) {
            console.error('[AIOS Daemon] Refusing to start A2A server: AIOS_A2A_TOKEN_SECRET is required');
        } else {
            const port = parseInt(a2aPort, 10);

            const agentCard: AgentCard = {
                id: process.env.AIOS_A2A_AGENT_ID ?? 'aios',
                name: process.env.AIOS_A2A_AGENT_NAME ?? 'AIOS',
                description: process.env.AIOS_A2A_AGENT_DESCRIPTION ?? 'AIOS Agent',
                capabilities: adapterRegistry.getAll().map((a) => a.id),
                endpoint: `http://${a2aHost}:${port}/tasks`,
            };

            const tokenExpiry = process.env.AIOS_A2A_TOKEN_EXPIRY
                ? Number(process.env.AIOS_A2A_TOKEN_EXPIRY)
                : undefined;

            a2aServer = new A2AServer({
                port,
                agentCard,
                tokenSecret: a2aTokenSecret,
                tokenExpiry: Number.isFinite(tokenExpiry) ? tokenExpiry : undefined,
            });

            a2aServer.on('task', async (event: { taskId: string; message: { payload: unknown }; clientId: string }) => {
                const { taskId, message, clientId } = event;

                const payload = message.payload as any;
                const prompt =
                    typeof payload === 'string'
                        ? payload
                        : typeof payload?.prompt === 'string'
                            ? payload.prompt
                            : typeof payload?.text === 'string'
                                ? payload.text
                                : (() => {
                                    try {
                                        return JSON.stringify(payload);
                                    } catch {
                                        return String(payload);
                                    }
                                })();

                try {
                    const dbTask = sessionManager.createTask(prompt, 'simple', {
                        source: 'a2a',
                        a2aTaskId: taskId,
                        clientId,
                    });

                    a2aTaskIdByAiosTaskId.set(dbTask.id, taskId);

                    await scheduler.submit(prompt, {
                        id: dbTask.id,
                        metadata: {
                            source: 'a2a',
                            a2aTaskId: taskId,
                            clientId,
                        },
                    });
                } catch (error) {
                    const errMsg = error instanceof Error ? error.message : String(error);
                    a2aServer?.updateTaskStatus(taskId, 'failed', undefined, errMsg);
                }
            });

            await a2aServer.start(port, a2aHost);
            console.error(`[AIOS Daemon] A2A server started on http://${a2aHost}:${port}`);
        }
    }

    console.error('[AIOS Daemon] Ready');

    // 优雅关闭
    process.on('SIGINT', async () => {
        console.error('[AIOS Daemon] Shutting down...');
        if (wsTransport) {
            await wsTransport.stop();
        }
        mcpServer?.stop();
        a2aServer?.stop();
        await adapterRegistry.shutdownAll();
        process.exit(0);
    });
}

main().catch((error) => {
    console.error('[AIOS Daemon] Fatal error:', error);
    process.exit(1);
});
