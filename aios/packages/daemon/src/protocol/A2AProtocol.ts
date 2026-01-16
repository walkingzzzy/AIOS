import { EventEmitter } from 'events';
import { A2ATokenManager, TokenValidationResult } from './A2ATokenManager.js';

export interface AgentCard {
    id: string;
    name: string;
    description: string;
    capabilities: string[];
    endpoint: string;
}

export interface A2AMessage {
    type: 'task' | 'result' | 'error' | 'ping' | 'pong';
    taskId?: string;
    from: string;
    to: string;
    payload: any;
}

export class A2AProtocol extends EventEmitter {
    private agentId: string;
    private agentCard: AgentCard;
    private knownAgents = new Map<string, AgentCard>();
    private pendingTasks = new Map<string, { resolve: Function; reject: Function }>();
    private tokenManager: A2ATokenManager | null = null;
    private accessTokens = new Map<string, string>(); // agentId -> token

    constructor(agentCard: AgentCard) {
        super();
        this.agentId = agentCard.id;
        this.agentCard = agentCard;
    }

    /**
     * 设置 Token 管理器（可选，用于安全通信）
     */
    setTokenManager(tokenManager: A2ATokenManager): void {
        this.tokenManager = tokenManager;
    }

    /**
     * 设置访问其他 Agent 的 Token
     */
    setAccessToken(agentId: string, token: string): void {
        this.accessTokens.set(agentId, token);
    }

    getAgentCard(): AgentCard {
        return this.agentCard;
    }

    registerAgent(card: AgentCard): void {
        this.knownAgents.set(card.id, card);
    }

    unregisterAgent(agentId: string): void {
        this.knownAgents.delete(agentId);
        this.accessTokens.delete(agentId);
    }

    getKnownAgents(): AgentCard[] {
        return Array.from(this.knownAgents.values());
    }

    async sendTask(toAgentId: string, task: any): Promise<any> {
        const agent = this.knownAgents.get(toAgentId);
        if (!agent) throw new Error(`Unknown agent: ${toAgentId}`);

        const taskId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const message: A2AMessage = {
            type: 'task',
            taskId,
            from: this.agentId,
            to: toAgentId,
            payload: task,
        };

        return new Promise((resolve, reject) => {
            this.pendingTasks.set(taskId, { resolve, reject });
            this.sendMessage(agent.endpoint, message, toAgentId);
        });
    }

    async handleMessage(message: A2AMessage): Promise<void> {
        switch (message.type) {
            case 'task':
                this.emit('task', message);
                break;
            case 'result':
            case 'error':
                if (message.taskId && this.pendingTasks.has(message.taskId)) {
                    const { resolve, reject } = this.pendingTasks.get(message.taskId)!;
                    this.pendingTasks.delete(message.taskId);
                    message.type === 'result' ? resolve(message.payload) : reject(new Error(message.payload));
                }
                break;
            case 'ping':
                this.sendResponse(message.from, { type: 'pong', from: this.agentId, to: message.from, payload: this.agentCard });
                break;
        }
    }

    /**
     * 验证入站消息的 Token（如果启用了安全层）
     */
    async verifyIncomingMessage(authHeader: string | undefined): Promise<TokenValidationResult> {
        if (!this.tokenManager) {
            return { valid: true }; // 未启用安全层，允许通过
        }

        if (!authHeader?.startsWith('Bearer ')) {
            return { valid: false, error: 'Missing or invalid authorization header' };
        }

        const token = authHeader.replace('Bearer ', '');
        return this.tokenManager.validateToken(token);
    }

    sendResult(taskId: string, toAgentId: string, result: any): void {
        const agent = this.knownAgents.get(toAgentId);
        if (agent) {
            this.sendMessage(agent.endpoint, { type: 'result', taskId, from: this.agentId, to: toAgentId, payload: result }, toAgentId);
        }
    }

    sendError(taskId: string, toAgentId: string, error: string): void {
        const agent = this.knownAgents.get(toAgentId);
        if (agent) {
            this.sendMessage(agent.endpoint, { type: 'error', taskId, from: this.agentId, to: toAgentId, payload: error }, toAgentId);
        }
    }

    private async sendMessage(endpoint: string, message: A2AMessage, toAgentId?: string): Promise<void> {
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };

        // 如果有访问 Token，添加到请求头
        if (toAgentId && this.accessTokens.has(toAgentId)) {
            headers['Authorization'] = `Bearer ${this.accessTokens.get(toAgentId)}`;
        }

        await fetch(endpoint, {
            method: 'POST',
            headers,
            body: JSON.stringify(message),
        });
    }

    private async sendResponse(toAgentId: string, message: A2AMessage): Promise<void> {
        const agent = this.knownAgents.get(toAgentId);
        if (agent) await this.sendMessage(agent.endpoint, message, toAgentId);
    }
}