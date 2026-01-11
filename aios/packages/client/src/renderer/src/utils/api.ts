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
        const socket = new WebSocket('ws://localhost:8765');

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
};
