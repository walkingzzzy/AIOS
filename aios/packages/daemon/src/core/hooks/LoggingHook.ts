/**
 * LoggingHook - 日志记录 Hook
 * 记录任务执行的完整生命周期日志
 */

import { BaseHook } from './BaseHook.js';
import {
    HookPriority,
    type TaskStartEvent,
    type TaskProgress,
    type ToolCallInfo,
    type ToolResultInfo,
    type TaskCompleteEvent,
    type TaskErrorEvent,
} from './types.js';

/**
 * 日志级别
 */
type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/**
 * 日志记录 Hook
 */
export class LoggingHook extends BaseHook {
    private logLevel: LogLevel;

    constructor(options: { logLevel?: LogLevel } = {}) {
        super('LoggingHook', {
            description: '记录任务执行的完整生命周期日志',
            priority: HookPriority.HIGHEST, // 最高优先级，确保先记录
        });
        this.logLevel = options.logLevel ?? 'info';
    }

    private log(level: LogLevel, message: string, data?: unknown): void {
        const levels: LogLevel[] = ['debug', 'info', 'warn', 'error'];
        if (levels.indexOf(level) < levels.indexOf(this.logLevel)) {
            return;
        }

        const timestamp = new Date().toISOString();
        const prefix = `[${timestamp}] [LoggingHook] [${level.toUpperCase()}]`;

        if (data !== undefined) {
            console.log(`${prefix} ${message}`, data);
        } else {
            console.log(`${prefix} ${message}`);
        }
    }

    async onTaskStart(event: TaskStartEvent): Promise<void> {
        this.log('info', `Task started: ${event.taskId}`, {
            input: event.input.substring(0, 100) + (event.input.length > 100 ? '...' : ''),
            analysis: event.analysis?.taskType,
        });
    }

    async onProgress(progress: TaskProgress): Promise<void> {
        this.log('debug', `Task ${progress.taskId} progress: ${progress.percentage}%`, {
            step: `${progress.currentStep}/${progress.totalSteps}`,
            description: progress.stepDescription,
        });
    }

    async onToolCall(info: ToolCallInfo): Promise<void> {
        this.log('info', `Tool call: ${info.adapterId}.${info.capabilityId}`, {
            params: info.params,
        });
    }

    async onToolResult(info: ToolResultInfo): Promise<void> {
        if (info.success) {
            this.log('info', `Tool result: ${info.adapterId}.${info.capabilityId} ✓`, {
                duration: `${info.duration}ms`,
            });
        } else {
            this.log('warn', `Tool result: ${info.adapterId}.${info.capabilityId} ✗`, {
                error: info.error?.message,
                duration: `${info.duration}ms`,
            });
        }
    }

    async onTaskComplete(event: TaskCompleteEvent): Promise<void> {
        this.log('info', `Task completed: ${event.taskId}`, {
            success: event.result.success,
            duration: `${event.duration}ms`,
        });
    }

    async onTaskError(event: TaskErrorEvent): Promise<void> {
        this.log('error', `Task error: ${event.taskId}`, {
            error: event.error.message,
            recoverable: event.recoverable,
        });
    }
}
