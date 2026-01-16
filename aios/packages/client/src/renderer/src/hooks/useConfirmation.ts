/**
 * useConfirmation - 确认请求 Hook
 */

import { useState, useEffect, useCallback } from 'react';

export interface ConfirmationRequest {
    id: string;
    operation: string;
    riskLevel: 'medium' | 'high' | 'critical';
    description: string;
    details: Record<string, unknown>;
    createdAt: number;
    timeout: number;
}

export interface UseConfirmationResult {
    /** 待处理的确认请求列表 */
    pendingRequests: ConfirmationRequest[];
    /** 当前显示的请求 */
    currentRequest: ConfirmationRequest | null;
    /** 确认操作 */
    confirm: (requestId: string) => Promise<void>;
    /** 拒绝操作 */
    reject: (requestId: string, reason?: string) => Promise<void>;
    /** 关闭对话框 */
    dismiss: () => void;
}

export function useConfirmation(): UseConfirmationResult {
    const [pendingRequests, setPendingRequests] = useState<ConfirmationRequest[]>([]);
    const [currentRequest, setCurrentRequest] = useState<ConfirmationRequest | null>(null);

    // 确认
    const confirm = useCallback(async (requestId: string) => {
        try {
            await window.aios.respondConfirmation(requestId, true);
            setPendingRequests(prev => prev.filter(r => r.id !== requestId));
            setCurrentRequest(null);
        } catch (error) {
            console.error('Confirmation failed:', error);
        }
    }, []);

    // 拒绝
    const reject = useCallback(async (requestId: string, reason?: string) => {
        try {
            await window.aios.respondConfirmation(requestId, false, reason);
            setPendingRequests(prev => prev.filter(r => r.id !== requestId));
            setCurrentRequest(null);
        } catch (error) {
            console.error('Rejection failed:', error);
        }
    }, []);

    // 关闭
    const dismiss = useCallback(() => {
        setCurrentRequest(null);
    }, []);

    // 监听确认请求
    useEffect(() => {
        const unsubscribe = window.aios.onConfirmationRequest((request) => {
            setPendingRequests(prev => [...prev, request]);
            // 如果没有当前显示的请求，显示这个
            setCurrentRequest(curr => curr ?? request);
        });

        return unsubscribe;
    }, []);

    // 自动显示下一个请求
    useEffect(() => {
        if (!currentRequest && pendingRequests.length > 0) {
            setCurrentRequest(pendingRequests[0]);
        }
    }, [currentRequest, pendingRequests]);

    return {
        pendingRequests,
        currentRequest,
        confirm,
        reject,
        dismiss,
    };
}
