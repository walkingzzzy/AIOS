/**
 * useTaskQueue - 任务队列状态 Hook
 */

import { useState, useEffect, useCallback } from 'react';

export interface TaskStatus {
    taskId: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
    prompt: string;
    priority: number;
    createdAt?: number;
    startedAt?: number;
    completedAt?: number;
    executionTime?: number;
    response?: string;
    error?: string;
}

export interface QueueStatus {
    pending: number;
    running: number;
    completed: number;
    failed: number;
    tasks: TaskStatus[];
}

export interface TaskProgressEvent {
    taskId: string;
    percentage: number;
    currentStep: number;
    totalSteps: number;
    stepDescription?: string;
}

export interface SubmitResult {
    taskId: string;
    status: string;
    position: number;
}

export interface UseTaskQueueResult {
    /** 队列状态 */
    queue: QueueStatus | null;
    /** 当前进度 */
    progress: Map<string, TaskProgressEvent>;
    /** 加载中 */
    loading: boolean;
    /** 错误 */
    error: string | null;
    /** 提交任务 */
    submit: (prompt: string, options?: {
        priority?: 'critical' | 'high' | 'normal' | 'low' | 'background';
        type?: 'simple' | 'visual' | 'complex';
    }) => Promise<SubmitResult>;
    /** 取消任务 */
    cancel: (taskId: string) => Promise<{ success: boolean; message: string }>;
    /** 刷新队列 */
    refresh: () => Promise<void>;
    /** 获取任务详情 */
    getTaskStatus: (taskId: string) => Promise<TaskStatus | null>;
}

export function useTaskQueue(): UseTaskQueueResult {
    const [queue, setQueue] = useState<QueueStatus | null>(null);
    const [progress, setProgress] = useState<Map<string, TaskProgressEvent>>(new Map());
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // 刷新队列状态
    const refresh = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const result = await window.aios.getTaskQueue();
            setQueue(result as QueueStatus);
        } catch (err) {
            setError(err instanceof Error ? err.message : '获取队列状态失败');
        } finally {
            setLoading(false);
        }
    }, []);

    // 提交任务
    const submit = useCallback(async (prompt: string, options?: {
        priority?: 'critical' | 'high' | 'normal' | 'low' | 'background';
        type?: 'simple' | 'visual' | 'complex';
    }): Promise<SubmitResult> => {
        const result = await window.aios.submitTask(prompt, options);
        // 提交后刷新队列
        setTimeout(refresh, 100);
        return result;
    }, [refresh]);

    // 取消任务
    const cancel = useCallback(async (taskId: string) => {
        const result = await window.aios.cancelTask(taskId);
        if (result.success) {
            setTimeout(refresh, 100);
        }
        return result;
    }, [refresh]);

    // 获取任务状态
    const getTaskStatus = useCallback(async (taskId: string): Promise<TaskStatus | null> => {
        return await window.aios.getTaskStatus(taskId) as TaskStatus | null;
    }, []);

    // 设置事件监听
    useEffect(() => {
        // 初始加载
        refresh();

        // 进度监听
        const unsubProgress = window.aios.onTaskProgress((event) => {
            setProgress(prev => {
                const next = new Map(prev);
                next.set(event.taskId, event);
                return next;
            });
        });

        // 完成监听
        const unsubComplete = window.aios.onTaskComplete(() => {
            refresh();
        });

        // 错误监听
        const unsubError = window.aios.onTaskError(() => {
            refresh();
        });

        return () => {
            unsubProgress();
            unsubComplete();
            unsubError();
        };
    }, [refresh]);

    return {
        queue,
        progress,
        loading,
        error,
        submit,
        cancel,
        refresh,
        getTaskStatus,
    };
}
