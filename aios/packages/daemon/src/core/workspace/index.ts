/**
 * Workspace 模块导出
 */

// 类型
export type {
    WorkspaceMode,
    WorkspaceConfig,
    WorkspaceMeta,
    WorkspaceStats,
    CleanupResult,
    CleanupPolicy,
    WorkspaceManagerConfig,
} from './types.js';

export { getDefaultWorkspaceConfig } from './types.js';

// 管理器
export { WorkspaceManager } from './WorkspaceManager.js';

// 清理服务
export { CleanupService } from './CleanupService.js';
