/**
 * Hook 系统导出
 */

// 核心类
export { BaseHook } from './BaseHook.js';
export { HookManager } from './HookManager.js';

// 内置 Hooks
export { LoggingHook } from './LoggingHook.js';
export { ProgressHook } from './ProgressHook.js';
export { CallbackHook } from './CallbackHook.js';
export type { CallbackEvent, CallbackEventType, CallbackHandler } from './CallbackHook.js';
export { MetricsHook } from './MetricsHook.js';
export type { AggregatedMetrics } from './MetricsHook.js';
export { PersistenceHook, type PersistenceHookConfig } from './PersistenceHook.js';

// 类型
export {
    HookPriority,
    type TaskStatus,
    type TaskProgress,
    type ToolCallInfo,
    type ToolResultInfo,
    type TaskStartEvent,
    type TaskCompleteEvent,
    type TaskErrorEvent,
    type HookMetadata,
} from './types.js';
