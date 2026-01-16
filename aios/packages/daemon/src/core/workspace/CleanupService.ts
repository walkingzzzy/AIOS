/**
 * CleanupService - 工作区清理服务
 */

import { WorkspaceManager } from './WorkspaceManager.js';
import type { CleanupPolicy, CleanupResult, WorkspaceMeta } from './types.js';

/**
 * 工作区清理服务
 */
export class CleanupService {
    private workspaceManager: WorkspaceManager;
    private cleanupTimer?: NodeJS.Timeout;

    constructor(workspaceManager: WorkspaceManager) {
        this.workspaceManager = workspaceManager;
    }

    /**
     * 执行清理
     */
    cleanup(policy: CleanupPolicy = {}): CleanupResult {
        const result: CleanupResult = {
            deleted: 0,
            freedBytes: 0,
            deletedIds: [],
        };

        const workspaces = this.workspaceManager.list();
        const now = Date.now();

        // 按最后访问时间排序（最旧的在前）
        const sorted = [...workspaces].sort((a, b) => a.lastAccessedAt - b.lastAccessedAt);

        // 收集待删除的工作区
        const toDelete: WorkspaceMeta[] = [];

        for (const ws of sorted) {
            // 只清理临时工作区
            if (policy.ephemeralOnly && ws.mode !== 'ephemeral') {
                continue;
            }

            // 检查年龄
            if (policy.maxAgeDays) {
                const ageDays = (now - ws.lastAccessedAt) / (24 * 60 * 60 * 1000);
                if (ageDays > policy.maxAgeDays) {
                    toDelete.push(ws);
                    continue;
                }
            }
        }

        // 检查数量限制
        if (policy.maxCount && workspaces.length > policy.maxCount) {
            const excess = workspaces.length - policy.maxCount;
            for (let i = 0; i < excess && i < sorted.length; i++) {
                const ws = sorted[i];
                if (!toDelete.includes(ws)) {
                    if (!policy.ephemeralOnly || ws.mode === 'ephemeral') {
                        toDelete.push(ws);
                    }
                }
            }
        }

        // 检查磁盘使用限制
        if (policy.maxDiskUsage) {
            const stats = this.workspaceManager.getStats();
            if (stats.activeDiskUsage > policy.maxDiskUsage) {
                let needToFree = stats.activeDiskUsage - policy.maxDiskUsage;
                for (const ws of sorted) {
                    if (needToFree <= 0) break;
                    if (!toDelete.includes(ws)) {
                        if (!policy.ephemeralOnly || ws.mode === 'ephemeral') {
                            toDelete.push(ws);
                            needToFree -= ws.sizeBytes;
                        }
                    }
                }
            }
        }

        // 执行删除
        for (const ws of toDelete) {
            if (this.workspaceManager.delete(ws.id)) {
                result.deleted++;
                result.freedBytes += ws.sizeBytes;
                result.deletedIds.push(ws.id);
            }
        }

        return result;
    }

    /**
     * 清理过期的临时工作区
     */
    cleanupExpired(maxAgeDays: number = 7): CleanupResult {
        return this.cleanup({
            maxAgeDays,
            ephemeralOnly: true,
        });
    }

    /**
     * 清理超出磁盘限制的工作区
     */
    cleanupByDiskUsage(maxDiskUsageGB: number): CleanupResult {
        return this.cleanup({
            maxDiskUsage: maxDiskUsageGB * 1024 * 1024 * 1024,
            ephemeralOnly: true,
        });
    }

    /**
     * 启动定时清理
     */
    startScheduledCleanup(intervalHours: number = 24, policy: CleanupPolicy = { maxAgeDays: 7, ephemeralOnly: true }): void {
        if (this.cleanupTimer) {
            clearInterval(this.cleanupTimer);
        }

        // 立即执行一次
        this.cleanup(policy);

        // 设置定时任务
        this.cleanupTimer = setInterval(() => {
            const result = this.cleanup(policy);
            if (result.deleted > 0) {
                console.log(`[CleanupService] Cleaned up ${result.deleted} workspaces, freed ${this.formatBytes(result.freedBytes)}`);
            }
        }, intervalHours * 60 * 60 * 1000);
    }

    /**
     * 停止定时清理
     */
    stopScheduledCleanup(): void {
        if (this.cleanupTimer) {
            clearInterval(this.cleanupTimer);
            this.cleanupTimer = undefined;
        }
    }

    /**
     * 格式化字节数
     */
    private formatBytes(bytes: number): string {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
        if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
        return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
    }

    /**
     * 获取清理建议
     */
    getSuggestions(): {
        suggestion: string;
        policy: CleanupPolicy;
        estimatedFreed: number;
    }[] {
        const suggestions: {
            suggestion: string;
            policy: CleanupPolicy;
            estimatedFreed: number;
        }[] = [];

        const workspaces = this.workspaceManager.list();
        const stats = this.workspaceManager.getStats();
        const now = Date.now();

        // 检查过期工作区
        const expired = workspaces.filter(ws => {
            const ageDays = (now - ws.lastAccessedAt) / (24 * 60 * 60 * 1000);
            return ageDays > 7 && ws.mode === 'ephemeral';
        });
        if (expired.length > 0) {
            const freedBytes = expired.reduce((sum, ws) => sum + ws.sizeBytes, 0);
            suggestions.push({
                suggestion: `发现 ${expired.length} 个超过 7 天未访问的临时工作区`,
                policy: { maxAgeDays: 7, ephemeralOnly: true },
                estimatedFreed: freedBytes,
            });
        }

        // 检查磁盘使用
        const usageGB = stats.activeDiskUsage / (1024 * 1024 * 1024);
        if (usageGB > 5) {
            suggestions.push({
                suggestion: `活跃工作区占用 ${usageGB.toFixed(2)} GB，建议清理`,
                policy: { maxDiskUsage: 5 * 1024 * 1024 * 1024 },
                estimatedFreed: stats.activeDiskUsage - 5 * 1024 * 1024 * 1024,
            });
        }

        return suggestions;
    }
}
