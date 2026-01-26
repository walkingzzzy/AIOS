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

// LLM Hooks
export { LLMMetricsHook } from './LLMMetricsHook.js';
export { LLMLoggingHook, type LogEntry, type LogLevel, type LLMLoggingConfig } from './LLMLoggingHook.js';
export { LLMCostTrackingHook, type CostRecord, type CostSummary, type ModelPricing, type LLMCostTrackingConfig } from './LLMCostTrackingHook.js';

// Event Bridge Hook
export { EventBridgeHook, type EventBridgeConfig } from './EventBridgeHook.js';

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
    // LLM 事件类型
    type LLMRequestEvent,
    type LLMResponseEvent,
    type LLMStreamChunkEvent,
    type PrepareRequestContext,
} from './types.js';
