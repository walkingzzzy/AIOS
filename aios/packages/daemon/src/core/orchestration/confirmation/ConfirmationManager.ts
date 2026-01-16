/**
 * ConfirmationManager - 用户确认管理器
 * 管理高风险操作的用户确认流程
 */

import { randomUUID } from 'crypto';
import type {
    ConfirmationRequest,
    ConfirmationStatus,
    ConfirmationHandler,
    ConfirmationManagerConfig,
} from './types.js';

/**
 * 用户确认管理器
 */
export class ConfirmationManager {
    /** 待确认请求队列 */
    private pendingRequests: Map<string, ConfirmationRequest>;

    /** 确认处理器（发送请求到客户端） */
    private handler?: ConfirmationHandler;

    /** 等待确认的 Promise */
    private waiters: Map<string, {
        resolve: (approved: boolean) => void;
        timer: NodeJS.Timeout;
    }>;

    /** 配置 */
    private config: Required<ConfirmationManagerConfig>;

    constructor(config: ConfirmationManagerConfig = {}) {
        this.pendingRequests = new Map();
        this.waiters = new Map();
        this.config = {
            timeout: config.timeout ?? 60000, // 60 秒默认超时
            autoApproveLowRisk: config.autoApproveLowRisk ?? false,
            enabled: config.enabled ?? true,
        };
    }

    /**
     * 设置确认处理器
     */
    setHandler(handler: ConfirmationHandler): void {
        this.handler = handler;
    }

    /**
     * 请求用户确认
     */
    async requestConfirmation(options: {
        taskId: string;
        sessionId?: string;
        action: string;
        riskLevel: 'low' | 'medium' | 'high' | 'critical';
        details?: Record<string, unknown>;
        timeout?: number;
    }): Promise<boolean> {
        // 如果禁用，直接通过
        if (!this.config.enabled) {
            return true;
        }

        // 低风险自动批准
        if (options.riskLevel === 'low' && this.config.autoApproveLowRisk) {
            return true;
        }

        const id = randomUUID();
        const now = Date.now();
        const timeout = options.timeout ?? this.config.timeout;

        const request: ConfirmationRequest = {
            id,
            taskId: options.taskId,
            sessionId: options.sessionId,
            action: options.action,
            riskLevel: options.riskLevel,
            details: options.details ?? {},
            status: 'pending',
            createdAt: now,
            expiresAt: now + timeout,
        };

        this.pendingRequests.set(id, request);

        // 发送确认请求到客户端
        if (this.handler) {
            try {
                const approved = await this.handler(request);
                this.handleResponse(id, approved);
                return approved;
            } catch (error) {
                console.error('[ConfirmationManager] Handler error:', error);
                this.handleTimeout(id);
                return false;
            }
        }

        // 如果没有处理器，等待手动响应
        return new Promise<boolean>((resolve) => {
            const timer = setTimeout(() => {
                this.handleTimeout(id);
                resolve(false);
            }, timeout);

            this.waiters.set(id, { resolve, timer });
        });
    }

    /**
     * 响应确认请求
     */
    respond(requestId: string, approved: boolean, comment?: string): boolean {
        const request = this.pendingRequests.get(requestId);
        if (!request || request.status !== 'pending') {
            return false;
        }

        this.handleResponse(requestId, approved, comment);
        return true;
    }

    /**
     * 获取待确认请求
     */
    getPending(sessionId?: string): ConfirmationRequest[] {
        const requests: ConfirmationRequest[] = [];
        for (const request of this.pendingRequests.values()) {
            if (request.status === 'pending') {
                if (!sessionId || request.sessionId === sessionId) {
                    requests.push(request);
                }
            }
        }
        return requests;
    }

    /**
     * 获取请求状态
     */
    getRequest(requestId: string): ConfirmationRequest | undefined {
        return this.pendingRequests.get(requestId);
    }

    /**
     * 取消请求
     */
    cancel(requestId: string): boolean {
        const waiter = this.waiters.get(requestId);
        if (waiter) {
            clearTimeout(waiter.timer);
            waiter.resolve(false);
            this.waiters.delete(requestId);
        }

        const request = this.pendingRequests.get(requestId);
        if (request) {
            request.status = 'rejected';
            return true;
        }
        return false;
    }

    /**
     * 批准所有待确认请求
     */
    approveAll(sessionId?: string): number {
        let count = 0;
        for (const [id, request] of this.pendingRequests) {
            if (request.status === 'pending') {
                if (!sessionId || request.sessionId === sessionId) {
                    this.respond(id, true);
                    count++;
                }
            }
        }
        return count;
    }

    /**
     * 拒绝所有待确认请求
     */
    rejectAll(sessionId?: string): number {
        let count = 0;
        for (const [id, request] of this.pendingRequests) {
            if (request.status === 'pending') {
                if (!sessionId || request.sessionId === sessionId) {
                    this.respond(id, false);
                    count++;
                }
            }
        }
        return count;
    }

    /**
     * 处理响应
     */
    private handleResponse(requestId: string, approved: boolean, comment?: string): void {
        const request = this.pendingRequests.get(requestId);
        if (request) {
            request.status = approved ? 'approved' : 'rejected';
            request.response = {
                approved,
                comment,
                respondedAt: Date.now(),
            };
        }

        const waiter = this.waiters.get(requestId);
        if (waiter) {
            clearTimeout(waiter.timer);
            waiter.resolve(approved);
            this.waiters.delete(requestId);
        }
    }

    /**
     * 处理超时
     */
    private handleTimeout(requestId: string): void {
        const request = this.pendingRequests.get(requestId);
        if (request && request.status === 'pending') {
            request.status = 'timeout';
        }
        this.waiters.delete(requestId);
    }

    /**
     * 清理过期请求
     */
    cleanup(): number {
        const now = Date.now();
        let count = 0;
        for (const [id, request] of this.pendingRequests) {
            if (request.status !== 'pending' || request.expiresAt < now) {
                // 保留 1 小时历史
                if (now - request.createdAt > 3600000) {
                    this.pendingRequests.delete(id);
                    count++;
                }
            }
        }
        return count;
    }

    /**
     * 获取统计
     */
    getStats(): {
        pending: number;
        approved: number;
        rejected: number;
        timeout: number;
    } {
        let pending = 0, approved = 0, rejected = 0, timeout = 0;
        for (const request of this.pendingRequests.values()) {
            switch (request.status) {
                case 'pending': pending++; break;
                case 'approved': approved++; break;
                case 'rejected': rejected++; break;
                case 'timeout': timeout++; break;
            }
        }
        return { pending, approved, rejected, timeout };
    }

    /**
     * 设置配置
     */
    setConfig(config: Partial<ConfirmationManagerConfig>): void {
        Object.assign(this.config, config);
    }

    /**
     * 获取配置
     */
    getConfig(): Required<ConfirmationManagerConfig> {
        return { ...this.config };
    }
}

/**
 * 默认实例
 */
export const confirmationManager = new ConfirmationManager();
