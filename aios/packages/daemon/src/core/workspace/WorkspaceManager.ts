/**
 * WorkspaceManager - 工作区管理器
 */

import { existsSync, mkdirSync, rmSync, readdirSync, statSync, writeFileSync, readFileSync, createWriteStream } from 'fs';
import { join, basename } from 'path';
import { homedir } from 'os';
import { randomUUID } from 'crypto';
import { createGzip } from 'zlib';
import { pipeline } from 'stream/promises';
import { createReadStream } from 'fs';
import type {
    WorkspaceConfig,
    WorkspaceMeta,
    WorkspaceStats,
    WorkspaceMode,
    WorkspaceManagerConfig,
} from './types.js';
import { getDefaultWorkspaceConfig } from './types.js';

/**
 * 工作区管理器
 */
export class WorkspaceManager {
    private config: WorkspaceConfig;

    constructor(managerConfig: WorkspaceManagerConfig = {}) {
        const rootDir = managerConfig.rootDir ?? join(homedir(), '.aios', 'workspaces');
        this.config = getDefaultWorkspaceConfig(rootDir);

        if (managerConfig.maxActiveAge) {
            this.config.maxActiveAge = managerConfig.maxActiveAge;
        }
        if (managerConfig.maxArchiveSizeGB) {
            this.config.maxArchiveSize = managerConfig.maxArchiveSizeGB * 1024 * 1024 * 1024;
        }

        this.ensureDirectories();
    }

    /**
     * 确保目录结构存在
     */
    private ensureDirectories(): void {
        const dirs = [
            this.config.rootDir,
            this.config.activeDir,
            this.config.archiveDir,
            this.config.tempDir,
        ];

        for (const dir of dirs) {
            if (!existsSync(dir)) {
                mkdirSync(dir, { recursive: true });
            }
        }
    }

    /**
     * 创建工作区
     */
    create(sessionId: string, mode: WorkspaceMode = 'ephemeral', options: {
        taskId?: string;
        userId?: string;
        description?: string;
        tags?: string[];
    } = {}): WorkspaceMeta {
        const id = randomUUID();
        const workspacePath = join(this.config.activeDir, id);

        mkdirSync(workspacePath, { recursive: true });

        const meta: WorkspaceMeta = {
            id,
            sessionId,
            taskId: options.taskId,
            userId: options.userId,
            mode,
            createdAt: Date.now(),
            lastAccessedAt: Date.now(),
            sizeBytes: 0,
            fileCount: 0,
            tags: options.tags,
            description: options.description,
            archived: false,
        };

        this.saveMeta(id, meta);
        return meta;
    }

    /**
     * 获取工作区路径
     */
    getPath(id: string): string {
        return join(this.config.activeDir, id);
    }

    /**
     * 获取工作区元信息
     */
    get(id: string): WorkspaceMeta | null {
        const metaPath = join(this.config.activeDir, id, 'meta.json');
        if (!existsSync(metaPath)) {
            return null;
        }

        try {
            const content = readFileSync(metaPath, 'utf-8');
            return JSON.parse(content) as WorkspaceMeta;
        } catch {
            return null;
        }
    }

    /**
     * 更新工作区访问时间
     */
    touch(id: string): void {
        const meta = this.get(id);
        if (meta) {
            meta.lastAccessedAt = Date.now();
            this.saveMeta(id, meta);
        }
    }

    /**
     * 更新工作区统计
     */
    updateStats(id: string): WorkspaceMeta | null {
        const meta = this.get(id);
        if (!meta) return null;

        const workspacePath = this.getPath(id);
        const stats = this.calculateDirStats(workspacePath);

        meta.sizeBytes = stats.size;
        meta.fileCount = stats.fileCount;
        meta.lastAccessedAt = Date.now();

        this.saveMeta(id, meta);
        return meta;
    }

    /**
     * 列出所有工作区
     */
    list(filter?: { mode?: WorkspaceMode; archived?: boolean }): WorkspaceMeta[] {
        const result: WorkspaceMeta[] = [];

        // 活跃工作区
        if (!filter?.archived) {
            const activeDir = this.config.activeDir;
            if (existsSync(activeDir)) {
                for (const name of readdirSync(activeDir)) {
                    const meta = this.get(name);
                    if (meta && (!filter?.mode || meta.mode === filter.mode)) {
                        result.push(meta);
                    }
                }
            }
        }

        return result.sort((a, b) => b.lastAccessedAt - a.lastAccessedAt);
    }

    /**
     * 归档工作区
     */
    async archive(id: string): Promise<string | null> {
        const meta = this.get(id);
        if (!meta) return null;

        const sourcePath = this.getPath(id);
        if (!existsSync(sourcePath)) return null;

        const archiveName = `${id}-${Date.now()}.tar.gz`;
        const archivePath = join(this.config.archiveDir, archiveName);

        try {
            // 简化实现：创建一个包含元信息的压缩文件
            // 实际应用中应该使用 tar 库
            const metaContent = JSON.stringify(meta, null, 2);
            const gzip = createGzip();
            const source = Buffer.from(metaContent);

            await new Promise<void>((resolve, reject) => {
                const output = createWriteStream(archivePath);
                gzip.pipe(output);
                gzip.write(source);
                gzip.end();
                output.on('finish', resolve);
                output.on('error', reject);
            });

            // 更新元信息
            meta.archived = true;
            meta.archivePath = archivePath;
            this.saveMeta(id, meta);

            return archivePath;
        } catch (error) {
            console.error('[WorkspaceManager] Archive failed:', error);
            return null;
        }
    }

    /**
     * 删除工作区
     */
    delete(id: string): boolean {
        const workspacePath = this.getPath(id);
        if (!existsSync(workspacePath)) return false;

        try {
            rmSync(workspacePath, { recursive: true, force: true });
            return true;
        } catch (error) {
            console.error('[WorkspaceManager] Delete failed:', error);
            return false;
        }
    }

    /**
     * 获取统计信息
     */
    getStats(): WorkspaceStats {
        const workspaces = this.list();

        let activeDiskUsage = 0;
        let archiveDiskUsage = 0;
        let archived = 0;

        for (const ws of workspaces) {
            if (ws.archived) {
                archived++;
                if (ws.archivePath && existsSync(ws.archivePath)) {
                    archiveDiskUsage += statSync(ws.archivePath).size;
                }
            } else {
                const stats = this.calculateDirStats(this.getPath(ws.id));
                activeDiskUsage += stats.size;
            }
        }

        // 归档目录统计
        if (existsSync(this.config.archiveDir)) {
            for (const name of readdirSync(this.config.archiveDir)) {
                const filePath = join(this.config.archiveDir, name);
                archiveDiskUsage += statSync(filePath).size;
            }
        }

        return {
            total: workspaces.length,
            active: workspaces.length - archived,
            archived,
            diskUsage: activeDiskUsage + archiveDiskUsage,
            activeDiskUsage,
            archiveDiskUsage,
        };
    }

    /**
     * 保存元信息
     */
    private saveMeta(id: string, meta: WorkspaceMeta): void {
        const metaPath = join(this.config.activeDir, id, 'meta.json');
        writeFileSync(metaPath, JSON.stringify(meta, null, 2));
    }

    /**
     * 计算目录统计
     */
    private calculateDirStats(dirPath: string): { size: number; fileCount: number } {
        let size = 0;
        let fileCount = 0;

        if (!existsSync(dirPath)) {
            return { size, fileCount };
        }

        const walk = (dir: string) => {
            try {
                const items = readdirSync(dir);
                for (const item of items) {
                    const fullPath = join(dir, item);
                    const stat = statSync(fullPath);
                    if (stat.isDirectory()) {
                        walk(fullPath);
                    } else {
                        size += stat.size;
                        fileCount++;
                    }
                }
            } catch {
                // 忽略权限错误等
            }
        };

        walk(dirPath);
        return { size, fileCount };
    }

    /**
     * 获取配置
     */
    getConfig(): WorkspaceConfig {
        return { ...this.config };
    }
}
