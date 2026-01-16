/**
 * ConfirmationManager - 用户确认管理器
 * 处理高风险操作的用户确认流程
 */

import type { AuditEvent } from '../core/orchestration/types.js';

/**
 * 确认请求
 */
export interface ConfirmationRequest {
    /** 请求 ID */
    id: string;
    /** 操作类型 */
    operation: string;
    /** 风险级别 */
    riskLevel: 'medium' | 'high' | 'critical';
    /** 操作描述 */
    description: string;
    /** 详细信息 */
    details: Record<string, unknown>;
    /** 创建时间 */
    createdAt: number;
    /** 超时时间 (ms) */
    timeout: number;
}

/**
 * 确认结果
 */
export interface ConfirmationResult {
    /** 是否确认 */
    confirmed: boolean;
    /** 确认者 */
    confirmedBy?: string;
    /** 确认时间 */
    confirmedAt?: number;
    /** 拒绝原因 */
    reason?: string;
}

/**
 * 确认回调
 */
export type ConfirmationCallback = (request: ConfirmationRequest) => Promise<ConfirmationResult>;

/**
 * IPC 事件发送器
 */
export type IPCEmitter = (channel: string, data: unknown) => void;

/**
 * 用户确认管理器
 */
export class ConfirmationManager {
    private pendingRequests: Map<string, ConfirmationRequest> = new Map();
    private resolvers: Map<string, (result: ConfirmationResult) => void> = new Map();
    private ipcEmitter?: IPCEmitter;
    private defaultTimeout: number = 30000; // 30 秒
    private requestCounter = 0;

    constructor(ipcEmitter?: IPCEmitter) {
        this.ipcEmitter = ipcEmitter;
    }

    /**
     * 设置 IPC 发送器
     */
    setIPCEmitter(emitter: IPCEmitter): void {
        this.ipcEmitter = emitter;
    }

    /**
     * 请求用户确认
     */
    async requestConfirmation(
        operation: string,
        description: string,
        riskLevel: ConfirmationRequest['riskLevel'],
        details: Record<string, unknown> = {}
    ): Promise<ConfirmationResult> {
        const request: ConfirmationRequest = {
            id: `confirm_${Date.now()}_${++this.requestCounter}`,
            operation,
            description,
            riskLevel,
            details,
            createdAt: Date.now(),
            timeout: this.defaultTimeout,
        };

        this.pendingRequests.set(request.id, request);

        // 通过 IPC 发送到前端
        if (this.ipcEmitter) {
            this.ipcEmitter('confirmation:request', request);
        }

        console.log(`[ConfirmationManager] Confirmation requested: ${operation}`);

        // 等待确认或超时
        return new Promise((resolve) => {
            this.resolvers.set(request.id, resolve);

            // 超时处理
            setTimeout(() => {
                if (this.pendingRequests.has(request.id)) {
                    this.pendingRequests.delete(request.id);
                    this.resolvers.delete(request.id);
                    resolve({
                        confirmed: false,
                        reason: 'Timeout',
                    });
                }
            }, request.timeout);
        });
    }

    /**
     * 处理用户响应（从前端接收）
     */
    handleResponse(
        requestId: string,
        confirmed: boolean,
        confirmedBy?: string,
        reason?: string
    ): boolean {
        const resolver = this.resolvers.get(requestId);
        if (!resolver) {
            console.warn(`[ConfirmationManager] No pending request: ${requestId}`);
            return false;
        }

        this.pendingRequests.delete(requestId);
        this.resolvers.delete(requestId);

        resolver({
            confirmed,
            confirmedBy,
            confirmedAt: Date.now(),
            reason,
        });

        console.log(`[ConfirmationManager] Response received: ${requestId}, confirmed: ${confirmed}`);
        return true;
    }

    /**
     * 检查是否需要确认
     */
    requiresConfirmation(riskLevel: string): boolean {
        return riskLevel === 'high' || riskLevel === 'critical';
    }

    /**
     * 获取待处理请求
     */
    getPendingRequests(): ConfirmationRequest[] {
        return Array.from(this.pendingRequests.values());
    }

    /**
     * 取消请求
     */
    cancelRequest(requestId: string): boolean {
        const resolver = this.resolvers.get(requestId);
        if (resolver) {
            resolver({
                confirmed: false,
                reason: 'Cancelled',
            });
            this.pendingRequests.delete(requestId);
            this.resolvers.delete(requestId);
            return true;
        }
        return false;
    }

    /**
     * 清除所有待处理请求
     */
    clearAll(): void {
        for (const [id, resolver] of this.resolvers) {
            resolver({
                confirmed: false,
                reason: 'Cleared',
            });
        }
        this.pendingRequests.clear();
        this.resolvers.clear();
    }
}
