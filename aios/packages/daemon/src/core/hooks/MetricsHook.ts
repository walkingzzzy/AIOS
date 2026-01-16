/**
 * MetricsHook - 性能指标 Hook
 * 收集任务和工具执行的性能指标
 */

import { BaseHook } from './BaseHook.js';
import {
    HookPriority,
    type TaskStartEvent,
    type ToolResultInfo,
    type TaskCompleteEvent,
    type TaskErrorEvent,
} from './types.js';

/**
 * 工具指标
 */
interface ToolMetrics {
    adapterId: string;
    capabilityId: string;
    totalCalls: number;
    successCount: number;
    failureCount: number;
    totalDuration: number;
    avgDuration: number;
    minDuration: number;
    maxDuration: number;
}

/**
 * 任务指标
 */
interface TaskMetrics {
    totalTasks: number;
    completedTasks: number;
    failedTasks: number;
    totalDuration: number;
    avgDuration: number;
}

/**
 * 汇总指标
 */
export interface AggregatedMetrics {
    tasks: TaskMetrics;
    tools: Map<string, ToolMetrics>;
    startTime: number;
    lastUpdateTime: number;
}

/**
 * 性能指标 Hook
 */
export class MetricsHook extends BaseHook {
    /** 工具指标 */
    private toolMetrics: Map<string, ToolMetrics> = new Map();

    /** 任务指标 */
    private taskMetrics: TaskMetrics = {
        totalTasks: 0,
        completedTasks: 0,
        failedTasks: 0,
        totalDuration: 0,
        avgDuration: 0,
    };

    /** 活跃任务开始时间 */
    private taskStartTimes: Map<string, number> = new Map();

    /** 指标收集开始时间 */
    private startTime: number = Date.now();

    /** 最后更新时间 */
    private lastUpdateTime: number = Date.now();

    constructor() {
        super('MetricsHook', {
            description: '收集任务和工具执行的性能指标',
            priority: HookPriority.LOWEST, // 最低优先级，不影响性能
        });
    }

    async onTaskStart(event: TaskStartEvent): Promise<void> {
        this.taskMetrics.totalTasks++;
        this.taskStartTimes.set(event.taskId, event.timestamp);
        this.lastUpdateTime = Date.now();
    }

    async onToolResult(info: ToolResultInfo): Promise<void> {
        const key = `${info.adapterId}.${info.capabilityId}`;
        let metrics = this.toolMetrics.get(key);

        if (!metrics) {
            metrics = {
                adapterId: info.adapterId,
                capabilityId: info.capabilityId,
                totalCalls: 0,
                successCount: 0,
                failureCount: 0,
                totalDuration: 0,
                avgDuration: 0,
                minDuration: Infinity,
                maxDuration: 0,
            };
            this.toolMetrics.set(key, metrics);
        }

        metrics.totalCalls++;
        if (info.success) {
            metrics.successCount++;
        } else {
            metrics.failureCount++;
        }

        metrics.totalDuration += info.duration;
        metrics.avgDuration = metrics.totalDuration / metrics.totalCalls;
        metrics.minDuration = Math.min(metrics.minDuration, info.duration);
        metrics.maxDuration = Math.max(metrics.maxDuration, info.duration);

        this.lastUpdateTime = Date.now();
    }

    async onTaskComplete(event: TaskCompleteEvent): Promise<void> {
        this.updateTaskMetrics(event.taskId, event.result.success, event.duration);
    }

    async onTaskError(event: TaskErrorEvent): Promise<void> {
        const startTime = this.taskStartTimes.get(event.taskId);
        const duration = startTime ? event.timestamp - startTime : 0;
        this.updateTaskMetrics(event.taskId, false, duration);
    }

    private updateTaskMetrics(taskId: string, success: boolean, duration: number): void {
        if (success) {
            this.taskMetrics.completedTasks++;
        } else {
            this.taskMetrics.failedTasks++;
        }

        this.taskMetrics.totalDuration += duration;
        const finishedTasks = this.taskMetrics.completedTasks + this.taskMetrics.failedTasks;
        this.taskMetrics.avgDuration = this.taskMetrics.totalDuration / finishedTasks;

        this.taskStartTimes.delete(taskId);
        this.lastUpdateTime = Date.now();
    }

    /**
     * 获取汇总指标
     */
    getMetrics(): AggregatedMetrics {
        return {
            tasks: { ...this.taskMetrics },
            tools: new Map(this.toolMetrics),
            startTime: this.startTime,
            lastUpdateTime: this.lastUpdateTime,
        };
    }

    /**
     * 获取任务成功率
     */
    getTaskSuccessRate(): number {
        const finished = this.taskMetrics.completedTasks + this.taskMetrics.failedTasks;
        if (finished === 0) return 0;
        return this.taskMetrics.completedTasks / finished;
    }

    /**
     * 获取工具成功率
     */
    getToolSuccessRate(adapterId?: string, capabilityId?: string): number {
        let totalCalls = 0;
        let successCount = 0;

        for (const [key, metrics] of this.toolMetrics) {
            if (adapterId && !key.startsWith(adapterId)) continue;
            if (capabilityId && !key.endsWith(capabilityId)) continue;

            totalCalls += metrics.totalCalls;
            successCount += metrics.successCount;
        }

        if (totalCalls === 0) return 0;
        return successCount / totalCalls;
    }

    /**
     * 获取最慢的工具
     */
    getSlowestTools(limit: number = 5): ToolMetrics[] {
        return Array.from(this.toolMetrics.values())
            .sort((a, b) => b.avgDuration - a.avgDuration)
            .slice(0, limit);
    }

    /**
     * 重置所有指标
     */
    reset(): void {
        this.toolMetrics.clear();
        this.taskMetrics = {
            totalTasks: 0,
            completedTasks: 0,
            failedTasks: 0,
            totalDuration: 0,
            avgDuration: 0,
        };
        this.taskStartTimes.clear();
        this.startTime = Date.now();
        this.lastUpdateTime = Date.now();
    }
}
