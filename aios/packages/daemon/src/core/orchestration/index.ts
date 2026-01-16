/**
 * Orchestrator-Worker 模块导出
 */

export { WorkerPool, type WorkerPoolConfig, type WorkerExecutor } from './WorkerPool.js';
export { TaskDecomposer } from './TaskDecomposer.js';
export { PromptGuard, promptGuard } from './PromptGuard.js';
export { AuditLogger } from './AuditLogger.js';
export type {
    WorkerStatus,
    SubTask,
    Worker,
    TaskDecomposition,
    MergeStrategy,
    MergeConfig,
    OrchestratorConfig,
    AuditEvent,
    InjectionCheckResult,
} from './types.js';

// 确认管理器
export {
    ConfirmationManager,
    confirmationManager,
    type ConfirmationStatus,
    type ConfirmationRequest,
    type ConfirmationHandler,
    type ConfirmationManagerConfig,
} from './confirmation/index.js';
