/**
 * ProgressHook - 进度追踪 Hook
 * 追踪任务进度，支持实时更新和事件订阅
 */

import { BaseHook } from './BaseHook.js';
import {
    HookPriority,
    type TaskStartEvent,
    type TaskProgress,
    type TaskCompleteEvent,
    type TaskErrorEvent,
    type TaskStatus,
} from './types.js';

/**
 * 任务进度状态
 */
interface TaskProgressState {
    taskId: string;
    status: TaskStatus;
    currentStep: number;
    totalSteps: number;
    percentage: number;
    stepDescription?: string;
    startTime: number;
    endTime?: number;
    error?: Error;
}

/**
 * 进度事件监听器
 */
type ProgressListener = (taskId: string, progress: TaskProgressState) => void;

/**
 * 进度追踪 Hook
 */
export class ProgressHook extends BaseHook {
    /** 任务进度状态 */
    private taskStates: Map<string, TaskProgressState> = new Map();

    /** 进度变化监听器 */
    private listeners: Set<ProgressListener> = new Set();

    constructor() {
        super('ProgressHook', {
            description: '追踪任务进度，支持实时更新',
            priority: HookPriority.HIGH,
        });
    }

    /**
     * 添加进度监听器
     */
    addListener(listener: ProgressListener): void {
        this.listeners.add(listener);
    }

    /**
     * 移除进度监听器
     */
    removeListener(listener: ProgressListener): void {
        this.listeners.delete(listener);
    }

    /**
     * 获取任务进度
     */
    getProgress(taskId: string): TaskProgressState | undefined {
        return this.taskStates.get(taskId);
    }

    /**
     * 获取所有活跃任务
     */
    getActiveTasks(): TaskProgressState[] {
        return Array.from(this.taskStates.values())
            .filter(s => s.status === 'running' || s.status === 'pending');
    }

    /**
     * 通知所有监听器
     */
    private notifyListeners(taskId: string, state: TaskProgressState): void {
        for (const listener of this.listeners) {
            try {
                listener(taskId, state);
            } catch (error) {
                console.error('[ProgressHook] Listener error:', error);
            }
        }
    }

    async onTaskStart(event: TaskStartEvent): Promise<void> {
        const state: TaskProgressState = {
            taskId: event.taskId,
            status: 'running',
            currentStep: 0,
            totalSteps: 1, // 默认 1 步，后续更新
            percentage: 0,
            startTime: event.timestamp,
        };
        this.taskStates.set(event.taskId, state);
        this.notifyListeners(event.taskId, state);
    }

    async onProgress(progress: TaskProgress): Promise<void> {
        const state = this.taskStates.get(progress.taskId);
        if (!state) return;

        state.currentStep = progress.currentStep;
        state.totalSteps = progress.totalSteps;
        state.percentage = progress.percentage;
        state.stepDescription = progress.stepDescription;

        this.notifyListeners(progress.taskId, state);
    }

    async onTaskComplete(event: TaskCompleteEvent): Promise<void> {
        const state = this.taskStates.get(event.taskId);
        if (!state) return;

        state.status = event.result.success ? 'completed' : 'failed';
        state.percentage = 100;
        state.endTime = event.timestamp;

        this.notifyListeners(event.taskId, state);

        // 完成后延迟清理状态
        setTimeout(() => {
            this.taskStates.delete(event.taskId);
        }, 60000); // 保留 1 分钟
    }

    async onTaskError(event: TaskErrorEvent): Promise<void> {
        const state = this.taskStates.get(event.taskId);
        if (!state) return;

        state.status = 'failed';
        state.error = event.error;
        state.endTime = event.timestamp;

        this.notifyListeners(event.taskId, state);
    }

    /**
     * 清理所有状态
     */
    clear(): void {
        this.taskStates.clear();
        this.listeners.clear();
    }
}
