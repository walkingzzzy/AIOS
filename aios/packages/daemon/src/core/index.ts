/**
 * Core 模块导出
 */

export { AdapterRegistry, adapterRegistry } from './AdapterRegistry.js';
export { JSONRPCHandler, type MethodHandler } from './JSONRPCHandler.js';
export { StdioTransport, WebSocketTransport } from './transports/index.js';

// 三层 AI 协调系统
export { TaskOrchestrator, type OrchestratorConfig } from './TaskOrchestrator.js';
export { ToolExecutor, type ToolExecutionResult } from './ToolExecutor.js';
export { IntentAnalyzer } from './IntentAnalyzer.js';
export { TaskPlanner } from './TaskPlanner.js';
export { ContextManager, type HistoryMessage } from './ContextManager.js';
export { IntentCache } from './IntentCache.js';

// Hook 系统
export {
    BaseHook,
    HookManager,
    HookPriority,
    LoggingHook,
    ProgressHook,
    CallbackHook,
    MetricsHook,
    type TaskStatus as HookTaskStatus,
    type TaskProgress,
    type ToolCallInfo,
    type ToolResultInfo,
    type TaskStartEvent,
    type TaskCompleteEvent,
    type TaskErrorEvent,
    type HookMetadata,
    type CallbackEvent,
    type CallbackEventType,
    type CallbackHandler,
    type AggregatedMetrics,
} from './hooks/index.js';

// 任务调度系统
export {
    TaskScheduler,
    type TaskSchedulerConfig,
    TaskPriority,
    TaskStatus,
    type Task,
    type TaskType as SchedulerTaskType,
    type TaskSubmitOptions,
    type TaskExecutor,
    type QueueStats,
    type SchedulerEvents,
} from './scheduler/index.js';

// 权限管理
export { PermissionManager, permissionManager, type PermissionCheckResult, type PermissionRequestResult, type PermissionRequirement } from './PermissionManager.js';

// 存储系统
export {
    SessionRepository,
    TaskRepository,
    MessageRepository,
    SessionManager,
    type SessionQueryOptions,
    type TaskQueryOptions,
    type MessageQueryOptions,
    type SessionManagerConfig,
    type FullSession,
    type SessionStatus,
    type SessionRecord,
    type StoredTaskStatus,
    type TaskRecord,
    type MessageRole,
    type MessageRecord,
    type ToolExecutionRecord,
    type PaginationOptions,
    type PaginatedResult,
} from './storage/index.js';

// 容错重试
export {
    RetryPolicy,
    RETRY_POLICIES,
    CheckpointManager,
    type ErrorType,
    type RetryPolicyConfig,
    type RetryContext,
    type RetryResult,
    type CheckpointState,
} from './resilience/index.js';

// 计划与 ReAct
export {
    PlanManager,
    ReActOrchestrator,
    type PlanManagerConfig,
    type ReActConfig,
    type ReActContext,
    type ActionExecutor,
    type StepStatus,
    type PlanStep,
    type KnownIssue,
    type TaskPlan,
    type ReActState,
    type ReflectionResult,
    type DecompositionResult,
} from './planning/index.js';

// Skills 系统
export {
    SkillRegistry,
    ProjectMemoryManager,
    type SkillRegistryConfig,
    type ProjectMemoryManagerConfig,
    type SkillCategory,
    type SkillMeta,
    type SkillInstructions,
    type SkillResources,
    type Skill,
    type SkillMatch,
    type SkillSummary,
    type ProjectMemory,
} from './skills/index.js';

// O-W 编排与安全
export {
    WorkerPool,
    TaskDecomposer,
    PromptGuard,
    promptGuard,
    AuditLogger,
    ConfirmationManager,
    confirmationManager,
    type WorkerPoolConfig,
    type WorkerExecutor,
    type WorkerStatus,
    type SubTask,
    type Worker,
    type TaskDecomposition,
    type MergeStrategy,
    type MergeConfig,
    type OrchestratorConfig as OWOrchestratorConfig,
    type AuditEvent,
    type InjectionCheckResult,
    type ConfirmationStatus,
    type ConfirmationRequest,
    type ConfirmationHandler,
    type ConfirmationManagerConfig,
} from './orchestration/index.js';

// 错误处理系统 (Phase 14)
export {
    ErrorCode,
    ERROR_MESSAGES,
    isRetryableError,
    getRetryAfter,
    AppError,
    ErrorHandler,
    errorHandler,
    type ErrorDetails,
    type ErrorHandleResult,
    type ErrorHandlerConfig,
} from './errors/index.js';

// 安全系统 (Phase 13)
export {
    CallbackAuthManager,
    callbackAuthManager,
    type CallbackAuthMethod,
    type CallbackAuth,
    type CallbackPayload,
    type SignedCallback,
    type SignatureVerifyResult,
    type CallbackAuthManagerConfig,
} from './security/index.js';

// 审计系统 (Phase 9)
export {
    ToolTraceRepository,
    ToolTraceHook,
    type ToolTraceStatus,
    type ToolTrace,
    type ToolTraceQueryOptions,
    type ToolTraceStats,
    type ToolTraceRepositoryConfig,
    type ToolTraceHookConfig,
} from './audit/index.js';

// 用量统计 (Phase 10)
export {
    UsageRepository,
    UsageHook,
    UsageService,
    DEFAULT_PRICING_TABLE,
    TIER_DEFAULT_MODELS,
    type AITier,
    type UsageRecord,
    type UsageStats,
    type UsageQueryOptions,
    type ModelPricing,
    type PricingTable,
    type UsageRepositoryConfig,
    type UsageHookConfig,
    type UsageServiceConfig,
    type DateRangeStats,
} from './usage/index.js';

// 链路追踪 (Phase 12)
export {
    TraceContextManager,
    traceContextManager,
    TraceLogger,
    createLogger,
    LOG_LEVELS,
    type TraceContext,
    type SpanInfo,
    type TraceContextManagerConfig,
    type TraceLoggerConfig,
    type LogEntry,
} from './trace/index.js';

// 工作区管理 (Phase 11)
export {
    WorkspaceManager,
    CleanupService,
    getDefaultWorkspaceConfig,
    type WorkspaceMode,
    type WorkspaceConfig,
    type WorkspaceMeta,
    type WorkspaceStats,
    type CleanupResult,
    type CleanupPolicy,
    type WorkspaceManagerConfig,
} from './workspace/index.js';
