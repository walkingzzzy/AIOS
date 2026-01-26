/**
 * LLMLoggingHook - LLM 日志记录 Hook
 * 详细记录 LLM 请求和响应，用于调试和审计
 */

import { BaseHook } from './BaseHook.js';
import { HookPriority } from './types.js';
import type {
    LLMRequestEvent,
    LLMResponseEvent,
    LLMStreamChunkEvent,
} from './types.js';

/** 日志级别 */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/** 日志条目 */
export interface LogEntry {
    timestamp: number;
    level: LogLevel;
    requestId: string;
    taskId?: string;
    engineId: string;
    model: string;
    type: 'request' | 'response' | 'stream-chunk';
    message: string;
    data?: Record<string, unknown>;
}

/** 日志配置 */
export interface LLMLoggingConfig {
    /** 是否记录请求消息内容 */
    logMessageContent?: boolean;
    /** 是否记录响应内容 */
    logResponseContent?: boolean;
    /** 是否记录流式块内容 */
    logStreamChunks?: boolean;
    /** 消息内容最大长度 */
    maxContentLength?: number;
    /** 日志级别 */
    level?: LogLevel;
    /** 最大日志条数 */
    maxLogs?: number;
    /** 自定义日志输出 */
    logger?: (entry: LogEntry) => void;
}

/**
 * LLM 日志记录 Hook
 */
export class LLMLoggingHook extends BaseHook {
    private logs: LogEntry[] = [];
    private config: Required<Omit<LLMLoggingConfig, 'logger'>> & { logger?: (entry: LogEntry) => void };

    constructor(config: LLMLoggingConfig = {}) {
        super('llm-logging', {
            description: '详细记录 LLM 请求和响应',
            priority: HookPriority.HIGH, // 高优先级，优先记录
        });

        this.config = {
            logMessageContent: config.logMessageContent ?? true,
            logResponseContent: config.logResponseContent ?? true,
            logStreamChunks: config.logStreamChunks ?? false,
            maxContentLength: config.maxContentLength ?? 500,
            level: config.level ?? 'info',
            maxLogs: config.maxLogs ?? 1000,
            logger: config.logger,
        };
    }

    /**
     * LLM 请求开始
     */
    async onLLMRequest(event: LLMRequestEvent): Promise<void> {
        const messagesSummary = this.config.logMessageContent
            ? event.messages.map(m => ({
                role: m.role,
                content: this.truncate(m.content),
            }))
            : `[${event.messages.length} messages]`;

        const entry: LogEntry = {
            timestamp: event.timestamp,
            level: this.config.level,
            requestId: event.requestId,
            taskId: event.taskId,
            engineId: event.engineId,
            model: event.model,
            type: 'request',
            message: `LLM Request to ${event.model}`,
            data: {
                messages: messagesSummary,
                tools: event.tools?.map(t => t.name),
                options: event.options,
            },
        };

        this.addLog(entry);
        this.output(entry);
    }

    /**
     * LLM 响应完成
     */
    async onLLMResponse(event: LLMResponseEvent): Promise<void> {
        const content = this.config.logResponseContent
            ? this.truncate(event.content)
            : `[${event.content.length} chars]`;

        const entry: LogEntry = {
            timestamp: event.timestamp,
            level: this.config.level,
            requestId: event.requestId,
            taskId: event.taskId,
            engineId: event.engineId,
            model: event.model,
            type: 'response',
            message: `LLM Response from ${event.model} (${event.latency}ms)`,
            data: {
                content,
                finishReason: event.finishReason,
                toolCalls: event.toolCalls?.map(tc => tc.name),
                usage: event.usage,
                latency: event.latency,
            },
        };

        this.addLog(entry);
        this.output(entry);
    }

    /**
     * 流式块事件
     */
    async onLLMStreamChunk(event: LLMStreamChunkEvent): Promise<void> {
        if (!this.config.logStreamChunks) return;

        const entry: LogEntry = {
            timestamp: event.timestamp,
            level: 'debug',
            requestId: event.requestId,
            taskId: event.taskId,
            engineId: event.engineId,
            model: '',
            type: 'stream-chunk',
            message: `Stream chunk #${event.chunkIndex}`,
            data: {
                content: event.content ? this.truncate(event.content, 100) : undefined,
                finished: event.finished,
                finishReason: event.finishReason,
            },
        };

        this.addLog(entry);
        this.output(entry);
    }

    /**
     * 获取所有日志
     */
    getLogs(): LogEntry[] {
        return [...this.logs];
    }

    /**
     * 按请求 ID 获取日志
     */
    getLogsByRequest(requestId: string): LogEntry[] {
        return this.logs.filter(l => l.requestId === requestId);
    }

    /**
     * 按任务 ID 获取日志
     */
    getLogsByTask(taskId: string): LogEntry[] {
        return this.logs.filter(l => l.taskId === taskId);
    }

    /**
     * 获取最近 N 条日志
     */
    getRecentLogs(count: number = 50): LogEntry[] {
        return this.logs.slice(-count);
    }

    /**
     * 清空日志
     */
    clearLogs(): void {
        this.logs = [];
    }

    /**
     * 导出日志为 JSON
     */
    exportLogs(): string {
        return JSON.stringify(this.logs, null, 2);
    }

    private addLog(entry: LogEntry): void {
        this.logs.push(entry);
        // 裁剪旧日志
        if (this.logs.length > this.config.maxLogs) {
            this.logs = this.logs.slice(-this.config.maxLogs);
        }
    }

    private output(entry: LogEntry): void {
        if (this.config.logger) {
            this.config.logger(entry);
        } else {
            const prefix = `[LLM ${entry.type.toUpperCase()}]`;
            const msg = `${prefix} [${entry.requestId}] ${entry.message}`;

            switch (entry.level) {
                case 'debug':
                    console.debug(msg, entry.data);
                    break;
                case 'info':
                    console.log(msg, entry.data);
                    break;
                case 'warn':
                    console.warn(msg, entry.data);
                    break;
                case 'error':
                    console.error(msg, entry.data);
                    break;
            }
        }
    }

    private truncate(text: string, maxLength?: number): string {
        const max = maxLength ?? this.config.maxContentLength;
        if (text.length <= max) return text;
        return text.slice(0, max) + `... [truncated, ${text.length} chars total]`;
    }
}
