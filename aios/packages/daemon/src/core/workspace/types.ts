/**
 * Workspace 模块类型定义
 */

/**
 * 工作区模式
 */
export type WorkspaceMode = 'ephemeral' | 'persistent';

/**
 * 工作区配置
 */
export interface WorkspaceConfig {
    /** 根目录 */
    rootDir: string;
    /** 活跃工作区目录 */
    activeDir: string;
    /** 归档目录 */
    archiveDir: string;
    /** 临时目录 */
    tempDir: string;
    /** 活跃工作区最大保留天数 */
    maxActiveAge: number;
    /** 归档最大大小（字节） */
    maxArchiveSize: number;
}

/**
 * 工作区元信息
 */
export interface WorkspaceMeta {
    /** 工作区 ID */
    id: string;
    /** 会话 ID */
    sessionId: string;
    /** 任务 ID */
    taskId?: string;
    /** 用户 ID */
    userId?: string;
    /** 模式 */
    mode: WorkspaceMode;
    /** 创建时间 */
    createdAt: number;
    /** 最后访问时间 */
    lastAccessedAt: number;
    /** 大小（字节） */
    sizeBytes: number;
    /** 文件数量 */
    fileCount: number;
    /** 标签 */
    tags?: string[];
    /** 描述 */
    description?: string;
    /** 是否已归档 */
    archived?: boolean;
    /** 归档路径 */
    archivePath?: string;
}

/**
 * 工作区统计
 */
export interface WorkspaceStats {
    /** 总数 */
    total: number;
    /** 活跃数 */
    active: number;
    /** 已归档数 */
    archived: number;
    /** 总磁盘使用（字节） */
    diskUsage: number;
    /** 活跃工作区磁盘使用 */
    activeDiskUsage: number;
    /** 归档磁盘使用 */
    archiveDiskUsage: number;
}

/**
 * 清理结果
 */
export interface CleanupResult {
    /** 删除的工作区数量 */
    deleted: number;
    /** 释放的空间（字节） */
    freedBytes: number;
    /** 删除的工作区 ID 列表 */
    deletedIds: string[];
}

/**
 * 清理策略
 */
export interface CleanupPolicy {
    /** 最大保留天数 */
    maxAgeDays?: number;
    /** 最大磁盘使用（字节） */
    maxDiskUsage?: number;
    /** 最大工作区数量 */
    maxCount?: number;
    /** 只清理临时工作区 */
    ephemeralOnly?: boolean;
}

/**
 * WorkspaceManager 配置
 */
export interface WorkspaceManagerConfig {
    /** 根目录（默认 ~/.aios/workspaces） */
    rootDir?: string;
    /** 活跃工作区最大保留天数 */
    maxActiveAge?: number;
    /** 归档最大大小（GB） */
    maxArchiveSizeGB?: number;
}

/**
 * 默认工作区配置
 */
export function getDefaultWorkspaceConfig(rootDir: string): WorkspaceConfig {
    return {
        rootDir,
        activeDir: `${rootDir}/active`,
        archiveDir: `${rootDir}/archive`,
        tempDir: `${rootDir}/temp`,
        maxActiveAge: 7, // 7 天
        maxArchiveSize: 10 * 1024 * 1024 * 1024, // 10 GB
    };
}
