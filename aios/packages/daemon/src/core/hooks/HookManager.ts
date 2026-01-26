/**
 * HookManager - Hook 管理器
 * 负责 Hook 的注册、执行和错误隔离
 */

import { BaseHook } from './BaseHook.js';
import type {
    TaskStartEvent,
    TaskProgress,
    ToolCallInfo,
    ToolResultInfo,
    TaskCompleteEvent,
    TaskErrorEvent,
    HookMetadata,
    LLMRequestEvent,
    LLMResponseEvent,
    LLMStreamChunkEvent,
    PrepareRequestContext,
} from './types.js';

/**
 * Hook 执行结果
 */
interface HookExecutionResult {
    hookName: string;
    success: boolean;
    error?: Error;
    duration: number;
}

/**
 * Hook 管理器
 * 管理所有 Hook 的注册、执行和生命周期
 */
export class HookManager {
    /** 已注册的 Hooks */
    private hooks: Map<string, BaseHook> = new Map();

    /** 是否启用 Hook 系统 */
    private enabled: boolean = true;

    /** 执行超时时间 (ms) */
    private timeout: number = 5000;

    constructor(options: { enabled?: boolean; timeout?: number } = {}) {
        this.enabled = options.enabled ?? true;
        this.timeout = options.timeout ?? 5000;
    }

    /**
     * 注册 Hook
     * @param hook Hook 实例
     * @throws 如果 Hook 名称已存在
     */
    register(hook: BaseHook): void {
        const name = hook.getName();
        if (this.hooks.has(name)) {
            throw new Error(`Hook "${name}" already registered`);
        }
        this.hooks.set(name, hook);
        console.log(`[HookManager] Registered hook: ${name}`);
    }

    /**
     * 注销 Hook
     * @param name Hook 名称
     * @returns 是否成功注销
     */
    unregister(name: string): boolean {
        const result = this.hooks.delete(name);
        if (result) {
            console.log(`[HookManager] Unregistered hook: ${name}`);
        }
        return result;
    }

    /**
     * 获取 Hook
     * @param name Hook 名称
     */
    getHook(name: string): BaseHook | undefined {
        return this.hooks.get(name);
    }

    /**
     * 获取所有 Hook 元数据
     */
    getAllMetadata(): HookMetadata[] {
        return Array.from(this.hooks.values()).map(h => h.getMetadata());
    }

    /**
     * 获取按优先级排序的 Hooks
     */
    private getSortedHooks(): BaseHook[] {
        return Array.from(this.hooks.values())
            .filter(h => h.isEnabled())
            .sort((a, b) => a.getPriority() - b.getPriority());
    }

    /**
     * 执行 Hook 方法（带错误隔离和超时）
     */
    private async executeHook(
        hook: BaseHook,
        method: string,
        ...args: unknown[]
    ): Promise<HookExecutionResult> {
        const hookName = hook.getName();
        const startTime = Date.now();

        try {
            const fn = (hook as unknown as Record<string, (...a: unknown[]) => Promise<void>>)[method];
            if (typeof fn !== 'function') {
                throw new Error(`Method ${method} not found on hook ${hookName}`);
            }

            // 带超时的执行
            await Promise.race([
                fn.apply(hook, args),
                new Promise<never>((_, reject) =>
                    setTimeout(() => reject(new Error(`Hook timeout after ${this.timeout}ms`)), this.timeout)
                ),
            ]);

            return {
                hookName,
                success: true,
                duration: Date.now() - startTime,
            };
        } catch (error) {
            const err = error instanceof Error ? error : new Error(String(error));
            console.error(`[HookManager] Hook "${hookName}.${method}" failed:`, err.message);
            return {
                hookName,
                success: false,
                error: err,
                duration: Date.now() - startTime,
            };
        }
    }

    /**
     * 并行执行所有 Hooks 的指定方法
     */
    private async executeAll(method: string, ...args: unknown[]): Promise<HookExecutionResult[]> {
        if (!this.enabled) {
            return [];
        }

        const hooks = this.getSortedHooks();
        if (hooks.length === 0) {
            return [];
        }

        // 按优先级分组执行（同优先级并行，不同优先级串行）
        const results: HookExecutionResult[] = [];
        const priorityGroups = new Map<number, BaseHook[]>();

        for (const hook of hooks) {
            const priority = hook.getPriority();
            if (!priorityGroups.has(priority)) {
                priorityGroups.set(priority, []);
            }
            priorityGroups.get(priority)!.push(hook);
        }

        // 按优先级顺序执行
        const sortedPriorities = Array.from(priorityGroups.keys()).sort((a, b) => a - b);
        for (const priority of sortedPriorities) {
            const group = priorityGroups.get(priority)!;
            const groupResults = await Promise.all(
                group.map(hook => this.executeHook(hook, method, ...args))
            );
            results.push(...groupResults);
        }

        return results;
    }

    // ============ 生命周期方法触发 ============

    /**
     * 触发 onTaskStart
     */
    async triggerTaskStart(event: TaskStartEvent): Promise<void> {
        await this.executeAll('onTaskStart', event);
    }

    /**
     * 触发 onProgress
     */
    async triggerProgress(progress: TaskProgress): Promise<void> {
        await this.executeAll('onProgress', progress);
    }

    /**
     * 触发 onToolCall
     */
    async triggerToolCall(info: ToolCallInfo): Promise<void> {
        await this.executeAll('onToolCall', info);
    }

    /**
     * 触发 onToolResult
     */
    async triggerToolResult(info: ToolResultInfo): Promise<void> {
        await this.executeAll('onToolResult', info);
    }

    /**
     * 触发 onTaskComplete
     */
    async triggerTaskComplete(event: TaskCompleteEvent): Promise<void> {
        await this.executeAll('onTaskComplete', event);
    }

    /**
     * 触发 onTaskError
     */
    async triggerTaskError(event: TaskErrorEvent): Promise<void> {
        await this.executeAll('onTaskError', event);
    }

    // ============ LLM 生命周期方法触发 ============

    /**
     * 触发 onLLMRequest - AI 请求前
     */
    async triggerLLMRequest(event: LLMRequestEvent): Promise<void> {
        await this.executeAll('onLLMRequest', event);
    }

    /**
     * 触发 onLLMResponse - AI 响应后
     */
    async triggerLLMResponse(event: LLMResponseEvent): Promise<void> {
        await this.executeAll('onLLMResponse', event);
    }

    /**
     * 触发 onLLMStreamChunk - 流式块接收
     */
    async triggerLLMStreamChunk(event: LLMStreamChunkEvent): Promise<void> {
        await this.executeAll('onLLMStreamChunk', event);
    }

    /**
     * 触发 onPrepareRequest - 请求准备（允许修改请求）
     */
    async triggerPrepareRequest(context: PrepareRequestContext): Promise<void> {
        await this.executeAll('onPrepareRequest', context);
    }

    /**
     * 启用 Hook 系统
     */
    enable(): void {
        this.enabled = true;
    }

    /**
     * 禁用 Hook 系统
     */
    disable(): void {
        this.enabled = false;
    }

    /**
     * 是否启用
     */
    isEnabled(): boolean {
        return this.enabled;
    }

    /**
     * 获取已注册 Hook 数量
     */
    size(): number {
        return this.hooks.size;
    }

    /**
     * 清空所有 Hooks
     */
    clear(): void {
        this.hooks.clear();
    }
}
