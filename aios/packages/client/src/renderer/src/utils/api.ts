/**
 * API 工具 - 支持 Electron IPC 和 WebSocket 两种模式
 */

let ws: WebSocket | null = null;
let wsPromise: Promise<WebSocket> | null = null;
let requestId = 0;
const pendingRequests = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();

// 重连配置
const RECONNECT_DELAY = 1000;
const MAX_RECONNECT_DELAY = 30000;
let reconnectAttempts = 0;
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;

function getWebSocketToken(): string | null {
    // 1) 运行时注入
    const globalToken = (globalThis as any).__AIOS_WEBSOCKET_TOKEN__;
    if (typeof globalToken === 'string' && globalToken.trim()) return globalToken.trim();

    // 2) localStorage（便于调试）
    try {
        const stored = globalThis.localStorage?.getItem('AIOS_WEBSOCKET_TOKEN');
        if (stored && stored.trim()) return stored.trim();
    } catch {
        // ignore
    }

    // 3) Vite 环境变量（构建时注入）
    const envToken = (import.meta as any).env?.VITE_AIOS_WEBSOCKET_TOKEN;
    if (typeof envToken === 'string' && envToken.trim()) return envToken.trim();

    return null;
}

function buildWebSocketUrl(): string {
    const token = getWebSocketToken();
    if (!token) {
        throw new Error(
            'Missing WebSocket token. Set localStorage AIOS_WEBSOCKET_TOKEN or VITE_AIOS_WEBSOCKET_TOKEN.'
        );
    }
    const encoded = encodeURIComponent(token);
    return `ws://localhost:8765/?token=${encoded}`;
}

/** 初始化 WebSocket 连接 */
function initWebSocket(): Promise<WebSocket> {
    // 如果已经有连接且是打开状态，直接返回
    if (ws && ws.readyState === WebSocket.OPEN) {
        return Promise.resolve(ws);
    }

    // 如果正在连接中，返回同一个 Promise
    if (wsPromise) {
        return wsPromise;
    }

    // 创建新连接
    wsPromise = new Promise((resolve, reject) => {
        let socket: WebSocket;
        try {
            socket = new WebSocket(buildWebSocketUrl());
        } catch (error) {
            reject(error);
            return;
        }

        socket.onopen = () => {
            console.log('[API] WebSocket connected');
            ws = socket;
            reconnectAttempts = 0; // 重置重连计数
            resolve(socket);
        };

        socket.onerror = (error) => {
            console.error('[API] WebSocket error:', error);
        };

        socket.onmessage = (event) => {
            try {
                const response = JSON.parse(event.data);
                const pending = pendingRequests.get(response.id);
                if (pending) {
                    pendingRequests.delete(response.id);
                    if (response.error) {
                        pending.reject(new Error(response.error.message));
                    } else {
                        pending.resolve(response.result);
                    }
                }
            } catch (e) {
                console.error('[API] Failed to parse response:', e);
            }
        };

        socket.onclose = (event) => {
            console.log('[API] WebSocket closed:', event.code, event.reason);
            ws = null;
            wsPromise = null;

            // 拒绝所有待处理的请求
            for (const [id, pending] of pendingRequests) {
                pending.reject(new Error('WebSocket connection closed'));
                pendingRequests.delete(id);
            }

            // 自动重连（非正常关闭时）
            if (event.code !== 1000) {
                scheduleReconnect();
            }
        };

        // 连接超时
        setTimeout(() => {
            if (socket.readyState === WebSocket.CONNECTING) {
                socket.close();
                wsPromise = null;
                reject(new Error('WebSocket connection timeout'));
                scheduleReconnect();
            }
        }, 5000);
    });

    wsPromise.catch(() => {
        wsPromise = null;
    });

    return wsPromise;
}

/** 安排重连 */
function scheduleReconnect(): void {
    if (reconnectTimeout) {
        return; // 已经有重连计划
    }

    const delay = Math.min(RECONNECT_DELAY * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
    reconnectAttempts++;

    console.log(`[API] Scheduling reconnect in ${delay}ms (attempt ${reconnectAttempts})`);

    reconnectTimeout = setTimeout(() => {
        reconnectTimeout = null;
        initWebSocket().catch(() => {
            // 重连失败，会在 onclose 中再次安排
        });
    }, delay);
}

/** 通过 WebSocket 调用 daemon */
async function callDaemonWS(method: string, params?: Record<string, unknown>): Promise<unknown> {
    const socket = await initWebSocket();
    const id = ++requestId;

    return new Promise((resolve, reject) => {
        pendingRequests.set(id, { resolve, reject });

        socket.send(JSON.stringify({
            jsonrpc: '2.0',
            id,
            method,
            params,
        }));

        setTimeout(() => {
            if (pendingRequests.has(id)) {
                pendingRequests.delete(id);
                reject(new Error('Request timeout'));
            }
        }, 30000);
    });
}

/** 检查是否在 Electron 环境 */
export function isElectron(): boolean {
    return typeof window !== 'undefined' && !!window.aios;
}

/** 统一 API 调用 */
export const api = {
    async getAdapters(): Promise<unknown> {
        if (isElectron()) {
            return window.aios.getAdapters();
        }
        return callDaemonWS('getAdapters');
    },

    async getAdaptersWithStatus(): Promise<unknown> {
        if (isElectron()) {
            return window.aios.getAdaptersWithStatus();
        }
        return callDaemonWS('getAdaptersWithStatus');
    },

    async getHealth(): Promise<unknown> {
        if (isElectron()) {
            return window.aios.getHealth();
        }
        return callDaemonWS('health.check');
    },

    async invoke(adapterId: string, capability: string, args: Record<string, unknown>): Promise<unknown> {
        if (isElectron()) {
            return window.aios.invoke(adapterId, capability, args);
        }
        return callDaemonWS('invoke', { adapterId, capability, args });
    },

    async chat(messages: Array<{ role: string; content: string }>): Promise<unknown> {
        if (isElectron()) {
            return window.aios.chat(messages);
        }
        return callDaemonWS('chat', { messages });
    },

    async smartChat(message: string, hasScreenshot = false): Promise<{
        success: boolean;
        response: string;
        tier: 'direct' | 'fast' | 'vision' | 'smart';
        executionTime: number;
        model?: string;
    }> {
        if (isElectron()) {
            return window.aios.smartChat(message, hasScreenshot) as Promise<{
                success: boolean;
                response: string;
                tier: 'direct' | 'fast' | 'vision' | 'smart';
                executionTime: number;
                model?: string;
            }>;
        }
        return callDaemonWS('smartChat', { message, hasScreenshot }) as Promise<{
            success: boolean;
            response: string;
            tier: 'direct' | 'fast' | 'vision' | 'smart';
            executionTime: number;
            model?: string;
        }>;
    },

    async getAIConfig(): Promise<unknown> {
        if (isElectron()) {
            return window.aios.getAIConfig();
        }
        return callDaemonWS('getAIConfig');
    },

    async setAIConfig(config: Record<string, unknown>): Promise<unknown> {
        if (isElectron()) {
            return window.aios.setAIConfig(config);
        }
        return callDaemonWS('setAIConfig', config);
    },

    async fetchModels(params: { baseUrl: string; apiKey?: string }): Promise<unknown> {
        if (isElectron()) {
            return window.aios.fetchModels(params);
        }
        return callDaemonWS('fetchModels', params);
    },

    async testAIConnection(params: { baseUrl: string; apiKey?: string; model: string }): Promise<unknown> {
        if (isElectron()) {
            return window.aios.testAIConnection(params);
        }
        return callDaemonWS('testAIConnection', params);
    },

    async checkPermission(level: 'public' | 'low' | 'medium' | 'high' | 'critical'): Promise<{
        granted: boolean;
        level: string;
        platform: string;
        details?: string;
    }> {
        if (isElectron()) {
            return window.aios.checkPermission(level);
        }
        return callDaemonWS('checkPermission', { level }) as Promise<{
            granted: boolean;
            level: string;
            platform: string;
            details?: string;
        }>;
    },

    async requestPermission(level: 'public' | 'low' | 'medium' | 'high' | 'critical'): Promise<{
        success: boolean;
        granted: boolean;
        message: string;
    }> {
        if (isElectron()) {
            return window.aios.requestPermission(level);
        }
        return callDaemonWS('requestPermission', { level }) as Promise<{
            success: boolean;
            granted: boolean;
            message: string;
        }>;
    },

    // ============ 任务管理 API ============

    async createTask(prompt: string, options?: { sessionId?: string }): Promise<{ taskId: string }> {
        if (isElectron() && (window.aios as any).createTask) {
            return (window.aios as any).createTask(prompt, options);
        }
        return callDaemonWS('task.create', { prompt, ...options }) as Promise<{ taskId: string }>;
    },

    async getTask(taskId: string): Promise<unknown> {
        if (isElectron() && (window.aios as any).getTask) {
            return (window.aios as any).getTask(taskId);
        }
        return callDaemonWS('task.get', { taskId });
    },

    async cancelTask(taskId: string): Promise<{ success: boolean }> {
        if (isElectron() && (window.aios as any).cancelTask) {
            return (window.aios as any).cancelTask(taskId);
        }
        return callDaemonWS('task.cancel', { taskId }) as Promise<{ success: boolean }>;
    },

    // ============ 系统信息 API ============

    async getVersion(): Promise<{ version: string }> {
        if (isElectron() && (window.aios as any).getVersion) {
            return (window.aios as any).getVersion();
        }
        return callDaemonWS('getVersion') as Promise<{ version: string }>;
    },

    async getEventStats(): Promise<unknown> {
        if (isElectron() && (window.aios as any).getEventStats) {
            return (window.aios as any).getEventStats();
        }
        return callDaemonWS('events.getStats');
    },

    // ============ MCP 配置 API ============

    async getMCPConfig(): Promise<{ enabled: boolean; port: number | null; host: string }> {
        if (isElectron() && (window.aios as any).getMCPConfig) {
            return (window.aios as any).getMCPConfig();
        }
        return callDaemonWS('mcp.getConfig') as Promise<{ enabled: boolean; port: number | null; host: string }>;
    },

    async getMCPStatus(): Promise<{ running: boolean; connectedClients: number; exposedTools: string[] }> {
        if (isElectron() && (window.aios as any).getMCPStatus) {
            return (window.aios as any).getMCPStatus();
        }
        return callDaemonWS('mcp.getStatus') as Promise<{ running: boolean; connectedClients: number; exposedTools: string[] }>;
    },

    async listMCPServers(): Promise<Array<{
        name: string;
        type: 'stdio' | 'websocket';
        command?: string;
        args?: string[];
        url?: string;
        status: 'disconnected' | 'connecting' | 'connected' | 'error';
        tools: string[];
        lastError?: string;
    }>> {
        if (isElectron() && (window.aios as any).listMCPServers) {
            return (window.aios as any).listMCPServers();
        }
        return callDaemonWS('mcp.listServers') as any;
    },

    async addMCPServer(config: {
        name: string;
        type: 'stdio' | 'websocket';
        command?: string;
        args?: string[];
        url?: string;
    }): Promise<{
        name: string;
        type: 'stdio' | 'websocket';
        status: string;
        tools: string[];
    }> {
        if (isElectron() && (window.aios as any).addMCPServer) {
            return (window.aios as any).addMCPServer(config);
        }
        return callDaemonWS('mcp.addServer', config) as any;
    },

    async removeMCPServer(name: string): Promise<{ success: boolean }> {
        if (isElectron() && (window.aios as any).removeMCPServer) {
            return (window.aios as any).removeMCPServer(name);
        }
        return callDaemonWS('mcp.removeServer', { name }) as Promise<{ success: boolean }>;
    },

    async testMCPConnection(name: string): Promise<{ success: boolean; tools?: string[]; error?: string }> {
        if (isElectron() && (window.aios as any).testMCPConnection) {
            return (window.aios as any).testMCPConnection(name);
        }
        return callDaemonWS('mcp.testConnection', { name }) as any;
    },

    async connectMCPServer(name: string): Promise<{ success: boolean; error?: string }> {
        if (isElectron() && (window.aios as any).connectMCPServer) {
            return (window.aios as any).connectMCPServer(name);
        }
        return callDaemonWS('mcp.connect', { name }) as any;
    },

    async disconnectMCPServer(name: string): Promise<{ success: boolean }> {
        if (isElectron() && (window.aios as any).disconnectMCPServer) {
            return (window.aios as any).disconnectMCPServer(name);
        }
        return callDaemonWS('mcp.disconnect', { name }) as Promise<{ success: boolean }>;
    },

    async getMCPExternalTools(): Promise<Array<{ serverName: string; toolName: string; description?: string }>> {
        if (isElectron() && (window.aios as any).getMCPExternalTools) {
            return (window.aios as any).getMCPExternalTools();
        }
        return callDaemonWS('mcp.getExternalTools') as any;
    },

    // ============ A2A 配置 API ============

    async getA2AConfig(): Promise<{ enabled: boolean; port: number | null; host: string }> {
        if (isElectron() && (window.aios as any).getA2AConfig) {
            return (window.aios as any).getA2AConfig();
        }
        return callDaemonWS('a2a.getConfig') as Promise<{ enabled: boolean; port: number | null; host: string }>;
    },

    async getA2AStatus(): Promise<{ running: boolean; tasksProcessed: number }> {
        if (isElectron() && (window.aios as any).getA2AStatus) {
            return (window.aios as any).getA2AStatus();
        }
        return callDaemonWS('a2a.getStatus') as Promise<{ running: boolean; tasksProcessed: number }>;
    },

    async getAgentCard(): Promise<{
        id: string;
        name: string;
        description: string;
        capabilities: string[];
        endpoint: string;
    }> {
        if (isElectron() && (window.aios as any).getAgentCard) {
            return (window.aios as any).getAgentCard();
        }
        return callDaemonWS('a2a.getAgentCard') as any;
    },

    async setAgentCard(params: {
        id?: string;
        name?: string;
        description?: string;
        capabilities?: string[];
    }): Promise<{ success: boolean; agentCard: any }> {
        if (isElectron() && (window.aios as any).setAgentCard) {
            return (window.aios as any).setAgentCard(params);
        }
        return callDaemonWS('a2a.setAgentCard', params) as any;
    },

    async generateA2AToken(clientId: string, skills?: string[]): Promise<{ success: boolean; token?: string; error?: string }> {
        if (isElectron() && (window.aios as any).generateA2AToken) {
            return (window.aios as any).generateA2AToken(clientId, skills);
        }
        return callDaemonWS('a2a.generateToken', { clientId, skills }) as any;
    },
};
