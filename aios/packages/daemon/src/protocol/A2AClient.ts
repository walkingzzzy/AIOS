import type { AgentCard, A2AMessage } from './A2AProtocol.js';
export interface A2AClientConfig {
    baseUrl: string;
    token?: string;
    clientId?: string;
    agentId?: string;
    timeoutMs?: number;
}
export class A2AClient {
    private baseUrl: string;
    private token?: string;
    private clientId: string;
    private agentId?: string;
    private timeoutMs: number;
    constructor(config: A2AClientConfig) {
        if (!config.baseUrl) {
            throw new Error('A2A baseUrl 不能为空');
        }
        this.baseUrl = config.baseUrl.replace(/\/+$/, '');
        this.token = config.token;
        this.clientId = config.clientId ?? 'aios-client';
        this.agentId = config.agentId;
        this.timeoutMs = config.timeoutMs ?? 15000;
    }
    setToken(token: string): void {
        this.token = token;
    }
    setAgentId(agentId: string): void {
        this.agentId = agentId;
    }
    async getAgentCard(): Promise<AgentCard> {
        const card = await this.request<AgentCard>('/.well-known/agent.json');
        this.agentId = card.id;
        return card;
    }
    async submitTask(payload: unknown, options?: { taskId?: string; to?: string; from?: string }): Promise<{ taskId: string; status: string }> {
        if (!this.token) {
            throw new Error('未配置 A2A Token，无法提交任务');
        }
        const message: A2AMessage = {
            type: 'task',
            from: options?.from ?? this.clientId,
            to: options?.to ?? this.agentId ?? 'unknown',
            payload,
        };
        if (options?.taskId) message.taskId = options.taskId;
        return this.request<{ taskId: string; status: string }>('/tasks', {
            method: 'POST',
            body: message,
            requireAuth: true,
        });
    }
    async getTaskStatus(taskId: string): Promise<{ taskId: string; status: string; result?: unknown; error?: string }> {
        if (!taskId) {
            throw new Error('taskId 不能为空');
        }
        return this.request(`/tasks/${encodeURIComponent(taskId)}`);
    }
    private async request<T>(path: string, init?: { method?: string; body?: unknown; requireAuth?: boolean }): Promise<T> {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);
        const headers: Record<string, string> = {};
        let body: string | undefined;
        if (init?.body !== undefined) {
            headers['Content-Type'] = 'application/json';
            body = JSON.stringify(init.body);
        }
        if (init?.requireAuth) {
            if (!this.token) throw new Error('未配置 A2A Token，无法进行鉴权请求');
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        try {
            const response = await fetch(new URL(path, this.baseUrl), {
                method: init?.method ?? 'GET',
                headers,
                body,
                signal: controller.signal,
            });
            const text = await response.text();
            const parsed = text ? this.safeJson(text) : undefined;
            if (!response.ok) {
                const detail = parsed && typeof parsed === 'object' ? JSON.stringify(parsed) : text;
                throw new Error(`A2A 请求失败: ${response.status} ${response.statusText}${detail ? ` - ${detail}` : ''}`);
            }
            return (parsed ?? {}) as T;
        } finally {
            clearTimeout(timeoutId);
        }
    }
    private safeJson(text: string): unknown {
        try {
            return JSON.parse(text);
        } catch {
            return text;
        }
    }
}
