/**
 * BaseHook 抽象类
 * 所有 Hook 的基类，定义生命周期方法
 */

import {
    HookPriority,
    type HookMetadata,
    type TaskStartEvent,
    type TaskProgress,
    type ToolCallInfo,
    type ToolResultInfo,
    type TaskCompleteEvent,
    type TaskErrorEvent,
} from './types.js';

/**
 * Hook 抽象基类
 * 提供任务执行生命周期的扩展点
 */
export abstract class BaseHook {
    /** Hook 元数据 */
    protected readonly metadata: HookMetadata;

    constructor(name: string, options: Partial<Omit<HookMetadata, 'name'>> = {}) {
        this.metadata = {
            name,
            description: options.description,
            priority: options.priority ?? HookPriority.NORMAL,
            enabled: options.enabled ?? true,
        };
    }

    /**
     * 获取 Hook 名称
     */
    getName(): string {
        return this.metadata.name;
    }

    /**
     * 获取 Hook 优先级
     */
    getPriority(): HookPriority {
        return this.metadata.priority;
    }

    /**
     * 是否启用
     */
    isEnabled(): boolean {
        return this.metadata.enabled;
    }

    /**
     * 启用 Hook
     */
    enable(): void {
        this.metadata.enabled = true;
    }

    /**
     * 禁用 Hook
     */
    disable(): void {
        this.metadata.enabled = false;
    }

    /**
     * 获取元数据
     */
    getMetadata(): Readonly<HookMetadata> {
        return { ...this.metadata };
    }

    // ============ 生命周期方法 ============

    /**
     * 任务开始时调用
     * @param event 任务开始事件
     */
    async onTaskStart(_event: TaskStartEvent): Promise<void> {
        // 默认空实现，子类可覆盖
    }

    /**
     * 任务进度更新时调用
     * @param progress 进度信息
     */
    async onProgress(_progress: TaskProgress): Promise<void> {
        // 默认空实现，子类可覆盖
    }

    /**
     * 工具调用前调用
     * @param info 工具调用信息
     */
    async onToolCall(_info: ToolCallInfo): Promise<void> {
        // 默认空实现，子类可覆盖
    }

    /**
     * 工具执行完成后调用
     * @param info 工具执行结果
     */
    async onToolResult(_info: ToolResultInfo): Promise<void> {
        // 默认空实现，子类可覆盖
    }

    /**
     * 任务完成时调用
     * @param event 任务完成事件
     */
    async onTaskComplete(_event: TaskCompleteEvent): Promise<void> {
        // 默认空实现，子类可覆盖
    }

    /**
     * 任务出错时调用
     * @param event 任务错误事件
     */
    async onTaskError(_event: TaskErrorEvent): Promise<void> {
        // 默认空实现，子类可覆盖
    }
}
